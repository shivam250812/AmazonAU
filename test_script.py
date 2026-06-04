import asyncio
import os
from playwright.async_api import async_playwright
import sys

# Import existing functions
from chrome_profile import create_browser
from script import scrape_product

async def main():
    keyword = "monitor"
    print(f"Testing scraper with keyword: {keyword} (max 4 products)")
    
    # We will test against the US marketplace for this test
    os.environ["AMAZON_URL"] = "https://www.amazon.com/s?k="
    
    async with async_playwright() as p:
        # Launch browser (require_helium=False to make the test faster since we just want to test brand/price extraction)
        context = await create_browser(p, require_helium=False, is_setup_mode=False)
        
        page = await context.new_page()
        search_url = f"https://www.amazon.com/s?k={keyword}"
        print(f"Navigating to {search_url}...")
        
        await page.goto(search_url, timeout=60000)
        await page.wait_for_load_state("domcontentloaded")
        
        # Grab first 4 product links
        hrefs = await page.locator("a.a-link-normal.s-no-outline").evaluate_all(
            "elements => elements.map(e => e.getAttribute('href'))"
        )
        
        urls = []
        for href in hrefs:
            if href and "/dp/" in href:
                full_url = f"https://www.amazon.com{href.split('?')[0]}"
                if full_url not in urls:
                    urls.append(full_url)
            if len(urls) >= 4:
                break
                
        await page.close()
        
        print(f"Found {len(urls)} products to test.")
        
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Scraping: {url}")
            product = await scrape_product(context, url)
            if product:
                print(f"  -> ASIN: {product.get('asin')}")
                print(f"  -> Brand: {product.get('brand')}")
                print(f"  -> Price: {product.get('price')}")
                print(f"  -> Rating: {product.get('rating')} ({product.get('reviews')} reviews)")
                print(f"  -> Seller: {product.get('seller')} (Shipper: {product.get('shipper')})")
            else:
                print("  -> Failed to scrape.")
                
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
