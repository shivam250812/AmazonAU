import asyncio
from playwright.async_api import async_playwright
import sys

from chrome_profile import create_browser
from script import extract_helium10_revenue

async def main():
    print("--- Testing Helium 10 Extraction ---")
    async with async_playwright() as p:
        context = await create_browser(p, require_helium=True, is_setup_mode=False)
        page = await context.new_page()
        
        from helium_login import helium_auto_login
        
        print("\nChecking Helium 10 login status first...")
        await helium_auto_login(context)
        
        test_url = "https://www.amazon.com.au/dp/B08LVBV9KX"
        print(f"\nLoading {test_url} ...")
        await page.goto(test_url, timeout=60000, wait_until="domcontentloaded")
        
        print("Waiting 15 seconds for Helium 10 to inject its panel...")
        await page.wait_for_timeout(15000)
        
        print("Running Helium 10 extraction script...")
        revenue = await extract_helium10_revenue(page)
        
        print(f"\n=======================")
        print(f"HELIUM 10 REVENUE: {revenue}")
        print(f"=======================\n")
        
        print("Taking a screenshot for debugging...")
        await page.screenshot(path="helium_debug.png", full_page=True)
        print("Screenshot saved to helium_debug.png")
        
        await page.close()
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
