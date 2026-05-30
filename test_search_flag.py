import asyncio
from playwright.async_api import async_playwright
import time
from chrome_profile import create_browser

async def main():
    async with async_playwright() as p:
        context = await create_browser(p, require_helium=True, is_setup_mode=False)
        page = await context.new_page()
        
        from helium_login import helium_auto_login
        print("Logging into Helium 10 first...")
        await helium_auto_login(context)
        
        url = "https://www.amazon.com.au/s?k=brass+god+idols"
        print(f"Loading {url}...")
        start = time.time()
        await page.goto(url, timeout=60000)
        
        print("Waiting for Helium 10 injection on search results...")
        
        # Wait up to 15 seconds to see what gets injected
        for i in range(15):
            # Try to find images or spans with flags
            html = await page.content()
            if "h10" in html.lower() and "flag" in html.lower():
                print(f"Found Helium 10 flag data after {i} seconds!")
                break
            await asyncio.sleep(1)
            
        print(f"Total time elapsed: {time.time() - start:.2f}s")
        
        print("Waiting 15 seconds for Helium 10 to fetch data...")
        await page.wait_for_timeout(15000)
        
        print("Extracting innerText from products...")
        
        script = """
        () => {
            let results = [];
            let items = document.querySelectorAll('div[data-component-type="s-search-result"]');
            for(let i of items) {
                results.push(i.innerText);
            }
            return results;
        }
        """
        products_text = await page.evaluate(script)
        
        for i, text in enumerate(products_text[:5]):
            print(f"\\n--- PRODUCT {i+1} ---")
            print(text)
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
