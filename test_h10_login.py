import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://members.helium10.com/user/signin")
        await asyncio.sleep(3)
        html = await page.content()
        with open("h10_login_dump.html", "w") as f:
            f.write(html)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
