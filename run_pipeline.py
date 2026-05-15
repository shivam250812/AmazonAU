#!/usr/bin/env python3
"""
run_pipeline.py — One-click Amazon automation pipeline.

Chains all scripts in sequence:
  1. suggest_amazon_categories.py  → keywords
  2. script.py                     → output.csv  (Amazon scraper)
  3. extract_asins.py              → input.csv   (ASIN list)
  4. sellercentral.py              → gated_output.csv
  5. merge_results.py              → final_report.csv

Usage:
  # Full pipeline (test mode: 1 keyword, 1 page)
  python run_pipeline.py --test

  # Full pipeline with custom topic
  python run_pipeline.py --topic "copper water bottles"

  # Run in setup mode to install Helium 10 and log in
  python run_pipeline.py --setup

  # Full pipeline (all keywords, 20 pages each)
  python run_pipeline.py
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path


# All scripts live next to this file
_DIR = Path(__file__).resolve().parent
_PYTHON = sys.executable  # Use the same Python interpreter


# ─── Banners ───────────────────────────────────────────────────────────────────

def _banner(step: int, title: str):
    print(f"\n{'━' * 60}")
    print(f"  STEP {step} │ {title}")
    print(f"{'━' * 60}\n")


def _done_banner():
    print(f"\n{'═' * 60}")
    print(f"    PIPELINE COMPLETE")
    print(f"{'═' * 60}\n")


# ─── Step 1: Suggest Keywords ─────────────────────────────────────────────────

def step_suggest_keywords(
    topic: str,
    marketplace: str,
    count: int,
    test_mode: bool,
) -> list[str]:
    """
    Run suggest_amazon_categories.py and parse the JSON output.
    Returns a list of keyword strings.
    """
    _banner(1, "Suggest Amazon Keywords (AI)")

    cmd = [
        _PYTHON,
        str(_DIR / "suggest_amazon_categories.py"),
        "--topic", topic,
        "--marketplace", marketplace,
        "--count", str(count),
    ]

    print(f"  Running: {' '.join(cmd)}\n")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_DIR),
        timeout=120,
    )

    if result.returncode != 0:
        print(f" suggest_amazon_categories.py failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Parse the JSON output
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f" Could not parse suggestions output:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)

    suggestions = data.get("suggestions", [])
    keywords = [s["phrase"] for s in suggestions if "phrase" in s]

    if not keywords:
        print(" No keywords returned by suggest script.", file=sys.stderr)
        sys.exit(1)

    if test_mode:
        keywords = keywords[:1]
        print(f"   TEST MODE: Using only first keyword")

    print(f"   Keywords ({len(keywords)}):")
    for i, kw in enumerate(keywords, 1):
        print(f"     {i}. {kw}")

    return keywords


# ─── Step 2: Scrape Amazon ────────────────────────────────────────────────────

def step_scrape_amazon(keywords: list[str], test_mode: bool, min_price: str = None, max_price: str = None, pages: int = 20):
    """
    Run script.py with the given keywords.
    In test mode, sets SEARCH_PAGES=1.
    """
    _banner(2, "Scrape Amazon Products")

    env = os.environ.copy()
    if test_mode:
        env["SEARCH_PAGES"] = "1"
        print("   TEST MODE: Scraping only page 1 per keyword\n")
    else:
        env["SEARCH_PAGES"] = str(pages)
        print(f"   Scraping up to {pages} pages per keyword\n")

    keywords_str = ",".join(keywords)
    cmd = [
        _PYTHON,
        str(_DIR / "script.py"),
        "--keywords", keywords_str,
    ]

    if min_price:
        cmd.extend(["--min-price", str(min_price)])
    if max_price:
        cmd.extend(["--max-price", str(max_price)])

    print(f"  Running: {' '.join(cmd)}\n")

    result = subprocess.run(
        cmd,
        cwd=str(_DIR),
        env=env,
        timeout=3600,  # 1 hour max
    )

    if result.returncode != 0:
        print(" script.py failed.", file=sys.stderr)
        sys.exit(1)

    output_csv = _DIR / "output.csv"
    if not output_csv.exists() or output_csv.stat().st_size == 0:
        print(" output.csv was not created or is empty.", file=sys.stderr)
        sys.exit(1)

    print(f"\n   Scraper output: {output_csv}")


# ─── Step 3: Extract ASINs ────────────────────────────────────────────────────

def step_extract_asins():
    """Run extract_asins.py to produce input.csv from output.csv."""
    _banner(3, "Extract ASINs")

    # Import directly — it's a simple utility
    sys.path.insert(0, str(_DIR))
    from extract_asins import extract_asins

    asins = extract_asins(
        str(_DIR / "output.csv"),
        str(_DIR / "input.csv"),
    )

    if not asins:
        print("  No ASINs extracted — skipping Seller Central step.")
        return False

    return True


# ─── Step 4: Seller Central ───────────────────────────────────────────────────

def step_seller_central():
    """Run sellercentral.py to check gating for each ASIN."""
    _banner(4, "Check Seller Central Gating")

    cmd = [
        _PYTHON,
        str(_DIR / "sellercentral.py"),
        "--input-csv", str(_DIR / "input.csv"),
        "--output-csv", str(_DIR / "gated_output.csv"),
    ]

    print(f"  Running: {' '.join(cmd)}\n")

    result = subprocess.run(
        cmd,
        cwd=str(_DIR),
        timeout=3600,
    )

    if result.returncode != 0:
        print("  sellercentral.py returned non-zero. Continuing with merge...", file=sys.stderr)


# ─── Step 5: Merge Results ────────────────────────────────────────────────────

def step_merge():
    """Merge scraper output with gating results."""
    _banner(5, "Merge Final Report")

    sys.path.insert(0, str(_DIR))
    from merge_results import merge_results

    final = merge_results(
        str(_DIR / "output.csv"),
        str(_DIR / "gated_output.csv"),
        str(_DIR / "final_report.csv"),
    )

    print(f"\n   Final report: {final}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="One-click Amazon automation pipeline"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: use only the first keyword and scrape only page 1",
    )
    parser.add_argument(
        "--topic",
        default="handmade / artisan home and lifestyle products",
        help="Topic for keyword suggestion (passed to suggest_amazon_categories.py)",
    )
    parser.add_argument(
        "--marketplace",
        default="amazon.in",
        help="Target marketplace (default: amazon.in)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=12,
        help="Number of keyword suggestions to request (default: 12)",
    )
    parser.add_argument(
        "--keywords",
        type=str,
        default=None,
        help="Comma-separated keywords (skips the suggest step)",
    )
    parser.add_argument(
        "--skip-seller-central",
        action="store_true",
        help="Skip the Seller Central gating check",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Open browser in setup mode to install extensions and log in",
    )
    parser.add_argument(
        "--min-price",
        type=str,
        default=None,
        help="Minimum price filter for Amazon search",
    )
    parser.add_argument(
        "--max-price",
        type=str,
        default=None,
        help="Maximum price filter for Amazon search",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=20,
        help="Number of pages to scrape per keyword (default: 20)",
    )
    args = parser.parse_args()

    start = time.time()

    print("\n" + "═" * 60)
    print("    AMAZON ONE-CLICK PIPELINE")
    if args.test:
        print("    TEST MODE (1 keyword, 1 page)")
    if args.setup:
        print("     SETUP MODE")
    print("═" * 60)

    if args.setup:
        print("\n  Preparing fresh Chrome profile...")
        env = os.environ.copy()
        env["SETUP_ONLY"] = "1"
        subprocess.run(
            [_PYTHON, str(_DIR / "script.py")],
            env=env,
            cwd=str(_DIR)
        )
        print("\n   Setup complete. You can now run the pipeline.")
        return

    # Step 1: Get keywords
    if args.keywords:
        keywords = [kw.strip() for kw in args.keywords.split(",") if kw.strip()]
        if args.test:
            keywords = keywords[:1]
        _banner(1, "Using Provided Keywords (skipping AI suggest)")
        print(f"   Keywords ({len(keywords)}):")
        for i, kw in enumerate(keywords, 1):
            print(f"     {i}. {kw}")
    else:
        keywords = step_suggest_keywords(
            args.topic, args.marketplace, args.count, args.test
        )

    # Step 2: Scrape Amazon
    step_scrape_amazon(keywords, args.test, args.min_price, args.max_price, args.pages)

    # Step 3: Extract ASINs
    has_asins = step_extract_asins()

    # Step 4: Seller Central (only if we have ASINs)
    if has_asins and not args.skip_seller_central:
        step_seller_central()
    elif args.skip_seller_central:
        print("\n    Skipping Seller Central (--skip-seller-central)")

    # Step 5: Merge
    step_merge()

    elapsed = time.time() - start
    _done_banner()
    print(f"    Total time: {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"   Files created:")
    print(f"     • output.csv          — Scraper results")
    print(f"     • input.csv           — Extracted ASINs")
    print(f"     • gated_output.csv    — Seller Central gating")
    print(f"     • final_report.csv    — Merged final report")
    print()


if __name__ == "__main__":
    main()
