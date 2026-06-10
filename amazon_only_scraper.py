"""
script.py — Amazon product scraper with Helium 10 revenue extraction.

Usage:
  # Standalone with default keywords
  python script.py

  # With custom keywords (comma-separated)
  python script.py --keywords "copper bottle,standing desk"

  # From a JSON file (output of suggest_amazon_categories.py)
  python script.py --keywords-file suggestions.json

  # Limit search pages (for testing)
  SEARCH_PAGES=1 python script.py --keywords "copper bottle"
"""

import argparse
import random
import glob
from dotenv import load_dotenv

load_dotenv(override=True)
import asyncio
import json
import re
import csv
import os
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

# Shared Chrome profile setup
from chrome_profile import (
    CHROME_USER_DATA_DIR,
    PROFILE_DIR,
    create_browser,
    purge_helium10_storage,
)
from notifications import send_email_notification

# ─── Platform Safety ──────────────────────────────────────────────────────────
# Fix Unicode crashes on Windows terminals (cp1252 can't render special chars)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── Config ────────────────────────────────────────────────────────────────────

DEFAULT_KEYWORDS = ["copper water dispenser", "standing desk"]
BASE_URL = os.environ.get("AMAZON_URL", "https://www.amazon.com.au/s?k=").strip()
if not BASE_URL.endswith("=") and "s?k" not in BASE_URL:
    if not BASE_URL.endswith("/"):
        BASE_URL += "/"
    BASE_URL += "s?k="
_OUTPUT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = str(_OUTPUT_DIR / "output.csv")

AMAZON_ORIGIN = f"{urlparse(BASE_URL).scheme}://{urlparse(BASE_URL).netloc}"
SETUP_ONLY = os.getenv("SETUP_ONLY", "0") == "1"
AUTO_CLEAN_HELIUM10 = os.getenv("AUTO_CLEAN_HELIUM10", "0") == "1"
HELIUM_LOGIN_FIRST = os.getenv("HELIUM_LOGIN_FIRST", "0") == "1"
HELIUM_LOGIN_ONLY = os.getenv("HELIUM_LOGIN_ONLY", "0") == "1"


# ─── Utility Functions ────────────────────────────────────────────────────────

def clean_price(text):
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"\d+\.?\d*", text)
    return float(match.group()) if match else None


def clean_money(text):
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"[$₹€£]?\s*(\d+\.?\d*)", text)
    return float(match.group(1)) if match else None


def extract_asin(url):
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    return match.group(1) if match else "N/A"

async def abort_media(route):
    try:
        if route.request.resource_type in ("image", "media", "font"):
            await route.abort()
        else:
            await route.continue_()
    except Exception:
        pass


# ─── Delivery Postcode ────────────────────────────────────────────────────────

DELIVERY_POSTCODE = os.getenv("DELIVERY_POSTCODE", "2000")


async def set_amazon_postcode(page, zipcode=None):
    """Set a consistent delivery postcode so prices/availability are stable."""
    zipcode = zipcode or DELIVERY_POSTCODE
    try:
        # Handle bot check "Continue shopping" button if it appears
        bot_btn = page.locator("button:has-text('Continue shopping'), input[value='Continue shopping']").first
        if await bot_btn.count():
            await bot_btn.click()
            await page.wait_for_timeout(3000)
            
        deliver_btn = page.locator(
            "#glow-ingress-block, #nav-global-location-popover-link"
        ).first
        if not await deliver_btn.count():
            return False
        await deliver_btn.click()
        await page.wait_for_timeout(2000)

        zip_input = page.locator("#GLUXZipUpdateInput, #GLUXPostalCodeWithCity_PostalCodeInput").first
        if not await zip_input.count():
            return False
        await zip_input.fill("")
        await zip_input.type(zipcode, delay=50)
        await page.wait_for_timeout(1000) # Wait for city dropdown to populate in AU

        # If the specific Australian city dropdown exists, select the first actual city (e.g., SYDNEY)
        city_dropdown = page.locator("#GLUXPostalCodeWithCity_DropdownList").first
        if await city_dropdown.count() and await city_dropdown.is_visible():
            try:
                # After typing postcode, it might take a moment to fetch cities
                await page.wait_for_timeout(2000)
                # Select the second option (index 1) since index 0 is "Select your City"
                await city_dropdown.select_option(index=1)
                await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"   Could not select city from dropdown: {e}")

        # The Apply button in Australia might not be in #GLUXZipUpdate
        apply_btn = page.locator(
            "#GLUXZipUpdate input[type='submit'], #GLUXZipUpdate .a-button-input, #GLUXPostalCodeWithCityApplyButton input, button:has-text('Apply'), input[aria-labelledby='GLUXZipUpdate-announce']"
        ).first
        if await apply_btn.count():
            await apply_btn.click()
            await page.wait_for_timeout(2000)

        # Close the confirmation popup if present (Continue or Done)
        try:
            done_btn = page.locator(
                "button[name='glowDoneButton'], #GLUXConfirmClose, button:has-text('Continue'), button:has-text('Done')"
            ).first
            if await done_btn.count():
                await done_btn.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        print(f"   Delivery postcode set to {zipcode}")
        return True
    except Exception as e:
        print(f"   Could not set delivery postcode: {e}")



# ─── Rating, Reviews, Sellers, Shipper/Seller ──────────────────────────────────

async def extract_rating_and_reviews(page):
    rating = None
    reviews = None
    try:
        alt = await page.locator("span.a-icon-alt").first.inner_text()
        m = re.search(r"(\d+(?:\.\d+)?)\s+out of 5", alt)
        if m:
            rating = float(m.group(1))
    except:
        pass

    try:
        txt = await page.locator("#acrCustomerReviewText").first.inner_text()
        m = re.search(r"([\d,]+)", txt)
        if m:
            reviews = int(m.group(1).replace(",", ""))
    except:
        pass

    return rating, reviews


async def extract_seller_count(page):
    """Best-effort seller count from Amazon offer listings."""
    for selector in [
        "#olp_feature_div",
        "#olpLinkWidget_feature_div",
        "div[id*='secondaryUsedAndNew']",
    ]:
        try:
            el = page.locator(selector).first
            if await el.count():
                txt = (await el.inner_text()).strip()
                m = re.search(r"\((\d+)\)", txt)
                if m:
                    return int(m.group(1))
        except:
            pass

    try:
        offers = page.locator("a[href*='offer-listing'], a[href*='offerlisting']")
        count = await offers.count()
        for i in range(min(count, 10)):
            txt = (await offers.nth(i).inner_text()) or ""
            m = re.search(r"New\s*\(\s*(\d+)\s*\)", txt, flags=re.IGNORECASE)
            if m:
                return int(m.group(1))
    except:
        pass

    try:
        buybox = page.locator("#buybox, #buyBoxAccordion, #moreBuyingChoices_feature_div")
        if await buybox.count():
            txt = (await buybox.first.inner_text()) or ""
            m = re.search(r"(\d+)\s+new", txt, flags=re.IGNORECASE)
            if m:
                return int(m.group(1))
    except:
        pass

    try:
        body = (await page.locator("body").inner_text()) or ""
        m = re.search(r"New\s*\(\s*(\d+)\s*\)\s*from", body, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+)\s+(?:new\s+)?offers?", body, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
    except:
        pass

    return None


async def extract_shipper_and_seller(page):
    """
    Best-effort extraction of Shipper and Seller from an Amazon product page.
    Returns (shipper, seller) strings, defaulting to "N/A".
    """
    shipper = "N/A"
    seller = "N/A"

    try:
        # Method 1: tabular buybox
        rows = page.locator(".tabular-buybox-row")
        row_count = await rows.count()
        if row_count > 0:
            for i in range(row_count):
                try:
                    row = rows.nth(i)
                    label_el = row.locator(".tabular-buybox-text, .tabular-buybox-label").first
                    value_el = row.locator(".tabular-buybox-text-message, .tabular-buybox-value-container").first
                    if not await label_el.count() or not await value_el.count():
                        continue
                    label_txt = (await label_el.inner_text()).strip().lower()
                    value_txt = (await value_el.inner_text()).strip()
                    if not value_txt:
                        continue
                    if "shipper" in label_txt and "seller" in label_txt:
                        shipper = value_txt
                        seller = value_txt
                    else:
                        if "ship" in label_txt:
                            shipper = value_txt
                        if "sold" in label_txt or "seller" in label_txt:
                            seller = value_txt
                except:
                    pass

        if shipper != "N/A" or seller != "N/A":
            return shipper, seller

        # Method 2: offer-display-feature (newer Amazon UI)
        labels = page.locator(".offer-display-feature-label")
        values = page.locator(".offer-display-feature-text")
        count = min(await labels.count(), await values.count())
        for i in range(count):
            try:
                label_txt = (await labels.nth(i).inner_text()).strip().lower()
                value_txt = (await values.nth(i).inner_text()).strip()
                # Use only the first line of the value text if multiple lines are present
                value_txt = value_txt.split("\n")[0].strip()
                if not value_txt:
                    continue
                if "shipper" in label_txt and "seller" in label_txt:
                    shipper = value_txt
                    seller = value_txt
                else:
                    if "ship" in label_txt:
                        shipper = value_txt
                    if "sold" in label_txt or "seller" in label_txt:
                        seller = value_txt
            except:
                pass

        if shipper != "N/A" or seller != "N/A":
            return shipper, seller

        # Method 3: buybox feature div regex
        for buybox_sel in ["#buybox", "#desktop_buybox", "#buyBoxAccordion", "#apex_desktop"]:
            try:
                box = page.locator(buybox_sel).first
                if not await box.count():
                    continue
                txt = (await box.inner_text()) or ""
                m = re.search(r"Shipper\s*/\s*Seller[:\s]+([^\n]+)", txt, re.IGNORECASE)
                if m:
                    val = m.group(1).strip().split("\n")[0].strip()
                    shipper = val
                    seller = val
                else:
                    m = re.search(r"Ships\s+from[:\s]+([^\n]+)", txt, re.IGNORECASE)
                    if m:
                        shipper = m.group(1).strip().split("\n")[0].strip()
                    m = re.search(r"Sold\s+by[:\s]+([^\n]+)", txt, re.IGNORECASE)
                    if m:
                        seller = m.group(1).strip().split("\n")[0].strip()
                if shipper != "N/A" or seller != "N/A":
                    break
            except:
                pass

        if shipper != "N/A" or seller != "N/A":
            return shipper, seller

        # Method 4: #merchant-info
        for sel in ["#merchant-info", "#soldByThirdParty", "#sellerProfileTriggerId"]:
            try:
                el = page.locator(sel).first
                if await el.count():
                    txt = (await el.inner_text()).strip()
                    if not txt:
                        continue
                    if sel == "#sellerProfileTriggerId":
                        seller = txt
                        if shipper == "N/A":
                            shipper = txt
                    else:
                        m = re.search(r"sold by\s+(.+?)(?:\.|$)", txt, re.IGNORECASE)
                        if m:
                            seller = m.group(1).strip()
                        m = re.search(r"ships from\s+(.+?)(?:\s+and|\.\band\b|$)", txt, re.IGNORECASE)
                        if m:
                            shipper = m.group(1).strip()
                    if seller != "N/A" or shipper != "N/A":
                        break
            except:
                pass

        if shipper != "N/A" or seller != "N/A":
            return shipper, seller

        # Method 5: full body scan
        try:
            body = (await page.locator("body").inner_text()) or ""
            m = re.search(r"Shipper\s*/\s*Seller[:\s]+([^\n]{2,60})", body, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                shipper = val
                seller = val
            else:
                m = re.search(r"Ships\s+from[:\s]+([^\n]{2,60})", body, re.IGNORECASE)
                if m:
                    shipper = m.group(1).strip()
                m = re.search(r"Sold\s+by[:\s]+([^\n]{2,60})", body, re.IGNORECASE)
                if m:
                    seller = m.group(1).strip()
        except:
            pass

    except Exception as e:
        print(f" extract_shipper_and_seller error: {e}")

    return shipper, seller


# ─── Brand Extraction ─────────────────────────────────────────────────────────

async def extract_brand(page):
    """
    Best-effort extraction of Brand from an Amazon product page.
    """
    brand = "N/A"
    
    # Method 1: Product Details table (.po-brand)
    try:
        for selector in [
            "tr.po-brand td.a-span9 span.a-size-base",
            "tr.po-brand td:nth-child(2) span",
            "#productOverview_feature_div tr.po-brand td.a-span9 span"
        ]:
            el = page.locator(selector).first
            if await el.count():
                txt = (await el.inner_text()).strip()
                if txt and txt.lower() != "n/a":
                    return txt
    except:
        pass

    # Method 2: Byline under title (e.g. "Visit the ASUS Store" or "Brand: ASUS")
    try:
        for selector in ["#bylineInfo", "#bylineInfo_feature_div a", "a#bylineInfo"]:
            els = page.locator(selector)
            count = await els.count()
            for i in range(count):
                txt = (await els.nth(i).inner_text()).strip()
                m = re.search(r"Visit the (.+?) Store", txt, re.IGNORECASE)
                if m:
                    return m.group(1).strip()
                m = re.search(r"Brand:\s+(.+)", txt, re.IGNORECASE)
                if m:
                    return m.group(1).strip()
    except:
        pass

    # Method 3: alt tag on brand logo
    try:
        el = page.locator("img#brandLogoHiResByline, img.premium-logoByLine-brand-logo").first
        if await el.count():
            alt = await el.get_attribute("alt")
            if alt:
                return alt.strip()
    except:
        pass

    return brand


# ─── Product Scraper ───────────────────────────────────────────────────────────

async def scrape_product(context, url):
    page = await context.new_page()
    page.set_default_timeout(3000)

    try:
        try:
            await page.route("**/*", abort_media)
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            # Smart wait for the buybox to attach
            try:
                await page.wait_for_selector("#buybox, #merchant-info, .tabular-buybox-text", state="attached", timeout=5000)
            except Exception:
                pass
        except Exception:
            return None

        price = None
        rating = None
        reviews = None
        sellers = None
        shipper = "N/A"
        seller = "N/A"
        brand = "N/A"

        try:
            price_locators = [
                "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
                "#corePrice_desktop .a-price .a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                ".a-price .a-offscreen",
                "span.a-color-price"
            ]
            for selector in price_locators:
                if await page.locator(selector).count() > 0:
                    price_text = await page.locator(selector).first.inner_text()
                    price = clean_price(price_text)
                    if price:
                        break
        except Exception:
            pass

        try:
            rating, reviews = await extract_rating_and_reviews(page)
        except Exception:
            pass
        try:
            sellers = await extract_seller_count(page)
        except Exception:
            pass
        try:
            shipper, seller = await extract_shipper_and_seller(page)
        except Exception:
            pass
        try:
            brand = await extract_brand(page)
        except Exception:
            pass

        asin = extract_asin(url)

        return {
            "asin": asin,
            "brand": brand,
            "price": price,
            "rating": rating,
            "reviews": reviews,
            "sellers": sellers,
            "shipper": shipper,
            "seller": seller,
            "url": url,
        }
    finally:
        try:
            await page.close()
        except Exception:
            pass


# ─── Keyword Processing ───────────────────────────────────────────────────────

import time
LAST_LOGIN_CHECK = 0

async def process_asins(context, asins, writer, out_fp):
    global LAST_LOGIN_CHECK
    if time.time() - LAST_LOGIN_CHECK > 3600:
        print("\n [Auto-Login] Periodic 1-hour verification of Amazon Seller Central session...")
        LAST_LOGIN_CHECK = time.time()
        try:
            from auto_login import amazon_auto_login
            await amazon_auto_login(context)
        except ImportError:
            pass

    urls = [f"{AMAZON_ORIGIN}/dp/{asin}" for asin in asins]

    semaphore = asyncio.Semaphore(4)
    write_lock = asyncio.Lock()

    async def bound_scrape(url):
        async with semaphore:
            product = await scrape_product(context, url)
            if not product:
                return

            print(
                f" ASIN: {product['asin']} | ${product['price']} "
                f"| Shipper: {product['shipper']} | Seller: {product['seller']}"
            )

            async with write_lock:
                writer.writerow([
                    product["asin"],
                    product["brand"],
                    product["price"],
                    product["rating"],
                    product["reviews"],
                    product["sellers"],
                    product["shipper"],
                    product["seller"],
                    product["url"],
                ])
                out_fp.flush()

    tasks = [bound_scrape(url) for url in urls]
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                print(f"      Product scrape error (skipped): {r}")


# ─── Public API (for run_pipeline.py) ──────────────────────────────────────────

async def run_scraper(asins: list[str]) -> str:
    """
    Run the full scraping pipeline for the given ASINs.
    Returns the path to the output CSV file.
    """
    async with async_playwright() as p:
        context = await create_browser(p)
        
        try:
            from auto_login import amazon_auto_login
            import time
            global LAST_LOGIN_CHECK
            print("\n [Auto-Login] Verifying Amazon Seller Central session...")
            await amazon_auto_login(context)
            LAST_LOGIN_CHECK = time.time()
        except ImportError:
            print("\n [Auto-Login] auto_login.py not found. Skipping Amazon auto-login.")

        if SETUP_ONLY:
            page = await context.new_page()
            await page.goto(AMAZON_ORIGIN, timeout=30000)
            print("\n SETUP MODE")
            print("1) Log into Amazon Seller Central.")
            print("2) You have ~5 minutes to complete this before the browser closes automatically.\n")
            print("   (Feel free to close the browser yourself when you are done!)")
            try:
                await page.wait_for_timeout(300_000)
                await context.close()
            except Exception:
                pass
            
            print("\n Setup complete. You can now run the pipeline.")
            return OUTPUT_FILE

        # Set a consistent delivery postcode for stable pricing
        if DELIVERY_POSTCODE:
            _pc_page = await context.new_page()
            try:
                await _pc_page.goto(
                    AMAZON_ORIGIN, timeout=30000, wait_until="domcontentloaded"
                )
                await set_amazon_postcode(_pc_page, DELIVERY_POSTCODE)
            except Exception as e:
                print(f"   Postcode setup failed (non-fatal): {e}")
            finally:
                pass
                try:
                    await _pc_page.close()
                except Exception:
                    pass

        file_exists = Path(OUTPUT_FILE).exists()
        mode = "a" if file_exists else "w"

        with open(OUTPUT_FILE, mode, newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "ASIN", "Brand", "Price", "Rating",
                    "Reviews", "Sellers", "Shipper", "Seller", "URL",
                ])
                f.flush()

            print(f"\n Writing rows to: {OUTPUT_FILE}\n")

            try:
                await process_asins(context, asins, writer, f)
            except Exception as e:
                if type(e).__name__ == "TargetClosedError":
                    print(
                        "\n Browser was closed before scraping finished.",
                        file=sys.stderr,
                    )
                else:
                    print(f"\n Error scraping ASINs: {e}", file=sys.stderr)

        await context.close()

    print(f"\n Done — output file: {OUTPUT_FILE}")
    return OUTPUT_FILE


# ─── CLI Entry Point ───────────────────────────────────────────────────────────

def _parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Amazon ASIN scraper")
    parser.add_argument(
        "--asins",
        type=str,
        default=None,
        help="Comma-separated list of ASINs to search",
    )
    parser.add_argument(
        "--asins-file",
        type=str,
        default=None,
        help="Path to CSV or TXT file with ASINs",
    )
    args = parser.parse_args()
    return args

def _get_asins(args) -> list[str]:
    if args.asins:
        return [kw.strip() for kw in args.asins.split(",") if kw.strip()]

    if args.asins_file:
        asins = []
        file_path = args.asins_file
        
        if file_path.lower().endswith('.csv'):
            import csv
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                
                # Find the exact name of the ASIN column (case-insensitive)
                if reader.fieldnames:
                    asin_key = None
                    for key in reader.fieldnames:
                        if key and key.strip().upper() == "ASIN":
                            asin_key = key
                            break
                            
                    if asin_key:
                        for row in reader:
                            val = row.get(asin_key)
                            if val and val.strip():
                                asins.append(val.strip())
                        return asins
                        
        # Fallback if it's not a standard CSV or has no ASIN header
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                for p in parts:
                    if p.strip() and p.strip().upper() != "ASIN":
                        asins.append(p.strip())
        return asins

    return ["B08LVBV9KX"]


async def main():
    args = _parse_args()
    asins = _get_asins(args)
    print(f" ASINs: {asins}\n")
    await run_scraper(asins)


if __name__ == "__main__":
    asyncio.run(main())