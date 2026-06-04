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

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# All scripts live next to this file
_DIR = Path(__file__).resolve().parent
_PYTHON = sys.executable  # Use the same Python interpreter


# ─── Banners ───────────────────────────────────────────────────────────────────

def _banner(step: int, title: str):
    print(f"\n{'-' * 60}")
    print(f"  STEP {step} | {title}")
    print(f"{'-' * 60}\n")


def _done_banner():
    print(f"\n{'=' * 60}")
    print(f"    PIPELINE COMPLETE")
    print(f"{'=' * 60}\n")


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
    Returns True on success, False on failure.
    """
    _banner(2, "Scrape Amazon Products")

    env = os.environ.copy()
    if test_mode:
        env["SEARCH_PAGES"] = "1"
        print("   TEST MODE: Scraping only page 1 per keyword\n")
    else:
        env["SEARCH_PAGES"] = str(pages)
        print(f"   Scraping up to {pages} pages per keyword\n")
        
    # Pass dynamic Amazon URL
    if "AMAZON_URL" not in env:
        # Default fallback
        env["AMAZON_URL"] = "https://www.amazon.com.au/s?k="

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
        timeout=None,  # No timeout for long scraping jobs
    )

    if result.returncode != 0:
        print(f"  script.py failed for this keyword. Skipping...", file=sys.stderr)
        return False

    output_csv = _DIR / "output.csv"
    if not output_csv.exists() or output_csv.stat().st_size == 0:
        print("  output.csv was not created or is empty. Skipping...", file=sys.stderr)
        return False

    print(f"\n   Scraper output: {output_csv}")
    return True


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

    env = os.environ.copy()
    # Pass along dynamic variables for Seller Central
    # Default fallbacks handled in sellercentral.py / auto_login.py if missing from env
    
    result = subprocess.run(
        cmd,
        cwd=str(_DIR),
        env=env,
        timeout=None,
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
        default="amazon.com.au",
        help="Target marketplace (default: amazon.com.au)",
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
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clear old CSV data before starting a new run",
    )
    
    # New dynamic URL arguments
    parser.add_argument("--amazon-url", type=str, default="https://www.amazon.com.au/s?k=", help="Base search URL for Amazon")
    parser.add_argument("--seller-login-url", type=str, default="https://sellercentral.amazon.com.au", help="Base login URL for Seller Central")
    parser.add_argument("--seller-url", type=str, default="https://sellercentral.amazon.com.au/product-search?ref_=myp_ps", help="Base search URL for Seller Central")
    parser.add_argument("--merchant-name", type=str, default="Shudhit", help="Merchant Name to select in Seller Central login")
    parser.add_argument("--merchant-country", type=str, default="Australia", help="Merchant Country to select in Seller Central login")
    
    args = parser.parse_args()

    start = time.time()

    print("\n" + "=" * 60)
    print("    AMAZON ONE-CLICK PIPELINE")
    if args.test:
        print("    TEST MODE (1 keyword, 1 page)")

    if args.setup:
        print("     SETUP MODE")
    print("=" * 60)

    if args.setup:
        print("\n  Preparing fresh Chrome profile...")
        env = os.environ.copy()
        env["SETUP_ONLY"] = "1"
        env["AMAZON_URL"] = args.amazon_url
        env["SELLER_CENTRAL_LOGIN_URL"] = args.seller_login_url
        env["SELLER_CENTRAL_URL"] = args.seller_url
        env["MERCHANT_NAME"] = args.merchant_name
        env["MERCHANT_COUNTRY"] = args.merchant_country
        
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

    # Clear old data if --fresh flag is used
    if args.fresh:
        for csv_name in ["output.csv", "input.csv", "gated_output.csv", "final_report.csv"]:
            csv_path = _DIR / csv_name
            if csv_path.exists():
                csv_path.unlink()
                print(f"   Deleted old {csv_name}")
        print()

    print(f"\n   Starting Keyword-by-Keyword Pipeline for {len(keywords)} keywords...")
    for i, kw in enumerate(keywords, 1):
        try:
            print(f"\n" + "=" * 50)
            print(f"   Processing Keyword {i}/{len(keywords)}: '{kw}'")
            print("=" * 50)

            # Step 2: Scrape Amazon
            # Set the env var here so step_scrape_amazon inherits it, or pass it directly.
            # We already use os.environ in step_scrape_amazon, so we set them globally for the script run
            os.environ["AMAZON_URL"] = args.amazon_url
            os.environ["SELLER_CENTRAL_LOGIN_URL"] = args.seller_login_url
            os.environ["SELLER_CENTRAL_URL"] = args.seller_url
            os.environ["MERCHANT_NAME"] = args.merchant_name
            os.environ["MERCHANT_COUNTRY"] = args.merchant_country
            
            scrape_ok = step_scrape_amazon([kw], args.test, args.min_price, args.max_price, args.pages)
            if not scrape_ok:
                print(f"   Skipping remaining steps for '{kw}'...")
                continue

            # Step 3: Extract ASINs
            has_asins = step_extract_asins()

            # Step 4: Seller Central (only if we have ASINs)
            if has_asins and not args.skip_seller_central:
                step_seller_central()
            elif args.skip_seller_central:
                print("\n    Skipping Seller Central (--skip-seller-central)")

            # Step 5: Merge
            step_merge()

            try:
                sys.path.insert(0, str(_DIR))
                from notifications import send_email_notification
                send_email_notification(
                    subject=f"Amazon Scraper: Keyword Complete - '{kw}'",
                    message=f"Processing for keyword '{kw}' ({i} of {len(keywords)}) has successfully finished and the results have been merged into the final report."
                )
            except Exception as notif_e:
                print(f"Could not send keyword completion notification: {notif_e}")

        except Exception as kw_err:
            print(f"\n   ERROR processing keyword '{kw}': {kw_err}")
            print(f"   Continuing to next keyword...\n")
            try:
                sys.path.insert(0, str(_DIR))
                from notifications import send_email_notification
                send_email_notification(
                    subject=f"Amazon Scraper: Keyword Failed - '{kw}'",
                    message=f"Keyword '{kw}' ({i} of {len(keywords)}) failed with error:\n{kw_err}\n\nContinuing to next keyword."
                )
            except Exception:
                pass

    elapsed = time.time() - start
    _done_banner()
    print(f"    Total time: {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"   Files created:")
    print(f"     • output.csv          — Scraper results")
    print(f"     • input.csv           — Extracted ASINs")
    print(f"     • gated_output.csv    — Seller Central gating")
    print(f"     • final_report.csv    — Merged final report")
    print()

    try:
        sys.path.insert(0, str(_DIR))
        from notifications import send_email_notification
        send_email_notification(
            subject="Amazon Scraper: Pipeline Finished Successfully! 🎉",
            message=f"The automation pipeline has completed successfully.\n\nTotal time: {elapsed / 60:.1f} minutes.\nKeywords processed: {len(keywords)}\n\nThe final report is ready at:\n{_DIR}/final_report.csv"
        )
    except Exception as notif_e:
        print(f"Could not send success notification: {notif_e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            # Import dynamically to avoid circular imports if any
            sys.path.insert(0, str(_DIR))
            from notifications import send_email_notification
            send_email_notification(
                subject="Amazon Scraper: Pipeline Stopped", 
                message=f"The pipeline encountered a fatal error:\n\n{traceback.format_exc()}"
            )
        except Exception as notif_e:
            print(f"Could not send failure notification: {notif_e}")
        sys.exit(1)
