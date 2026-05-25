"""
extract_asins.py — Extract unique ASINs from the scraper output CSV
and write them to a simple CSV for Seller Central.

Usage:
  python extract_asins.py                          # output.csv → input.csv
  python extract_asins.py --input output.csv --output input.csv
"""

import argparse
import csv
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def extract_asins(input_path: str = "output.csv", output_path: str = "input.csv") -> list[str]:
    """
    Read the scraper output CSV, extract unique ASINs, and write
    them to a single-column CSV with header 'ASIN'.

    Returns the list of unique ASINs.
    """
    asins_seen = set()
    asins_ordered = []

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                asin = (
                    row.get("ASIN")
                    or row.get("asin")
                    or row.get("Asin")
                    or ""
                ).strip()
                if asin and asin != "N/A" and asin not in asins_seen:
                    asins_seen.add(asin)
                    asins_ordered.append(asin)
    except FileNotFoundError:
        print(f" File not found: {input_path}", file=sys.stderr)
        return []

    if not asins_ordered:
        print(f"  No ASINs found in {input_path}")
        return []

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ASIN"])
        for asin in asins_ordered:
            writer.writerow([asin])

    print(f" Extracted {len(asins_ordered)} unique ASINs → {output_path}")
    return asins_ordered


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract ASINs from scraper output")
    parser.add_argument("--input", default="output.csv", help="Scraper output CSV")
    parser.add_argument("--output", default="input.csv", help="Output CSV with ASIN column")
    args = parser.parse_args()
    extract_asins(args.input, args.output)
