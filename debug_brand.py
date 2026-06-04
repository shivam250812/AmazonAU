import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://www.amazon.com/dp/B0DF786923")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            brand_html = await page.locator("tr.po-brand").evaluate("el => el.outerHTML")
            print("po-brand HTML:", brand_html)
        except Exception as e:
            print("po-brand not found:", e)
            
        try:
            byline = await page.locator("#bylineInfo").evaluate("el => el.outerHTML")
            print("byline HTML:", byline)
        except Exception as e:
            print("byline not found:", e)
            
        await browser.close()

asyncio.run(main())
