"""
merge_results.py — Merge scraper output with Seller Central gating results.

Joins output.csv and gated_output.csv on ASIN to produce final_report.csv.

Usage:
  python merge_results.py
  python merge_results.py --scraper output.csv --gated gated_output.csv --output final_report.csv
"""

import argparse
import csv
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def merge_results(
    scraper_csv: str = "output.csv",
    gated_csv: str = "gated_output.csv",
    output_csv: str = "final_report.csv",
) -> str:
    """
    Merge scraper results with gating data by ASIN.
    Returns path to the final merged CSV.
    """
    # ── Load gating data into a dict keyed by ASIN ────────────────────────
    gated_data = {}
    try:
        with open(gated_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                asin = (
                    row.get("ASIN")
                    or row.get("asin")
                    or row.get("Asin")
                    or ""
                ).strip()
                if asin:
                    gated_data[asin] = {
                        "status": row.get("STATUS", ""),
                        "message": row.get("MESSAGE", ""),
                    }
    except FileNotFoundError:
        print(f"  Gated output not found: {gated_csv} — merging without gating data")

    # ── Read scraper CSV and write merged output ──────────────────────────
    rows_written = 0
    try:
        with open(scraper_csv, "r", encoding="utf-8") as fin:
            reader = csv.DictReader(fin)
            scraper_fields = reader.fieldnames or []

            output_fields = scraper_fields + ["Gated_Status", "Gated_Message"]

            with open(output_csv, "w", newline="", encoding="utf-8") as fout:
                writer = csv.DictWriter(fout, fieldnames=output_fields)
                writer.writeheader()

                for row in reader:
                    asin = (
                        row.get("ASIN")
                        or row.get("asin")
                        or row.get("Asin")
                        or ""
                    ).strip()

                    gated = gated_data.get(asin, {})
                    row["Gated_Status"] = gated.get("status", "NOT_CHECKED")
                    row["Gated_Message"] = gated.get("message", "")

                    writer.writerow(row)
                    rows_written += 1

    except FileNotFoundError:
        print(f" Scraper output not found: {scraper_csv}", file=sys.stderr)
        return output_csv

    print(f" Merged {rows_written} rows → {output_csv}")

    # Show summary
    if gated_data:
        statuses = {}
        for g in gated_data.values():
            s = g.get("status", "UNKNOWN")
            statuses[s] = statuses.get(s, 0) + 1
        print(f"   Gating summary: {statuses}")

    return output_csv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge scraper + gating results")
    parser.add_argument("--scraper", default="output.csv", help="Scraper output CSV")
    parser.add_argument("--gated", default="gated_output.csv", help="Gated output CSV")
    parser.add_argument("--output", default="final_report.csv", help="Merged output path")
    args = parser.parse_args()
    merge_results(args.scraper, args.gated, args.output)
