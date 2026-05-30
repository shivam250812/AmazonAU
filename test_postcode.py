import asyncio
from playwright.async_api import async_playwright

from chrome_profile import create_browser

async def test_postcode():
    async with async_playwright() as p:
        context = await create_browser(p, require_helium=False, is_setup_mode=False)
        page = await context.new_page()
        
        await page.goto("https://www.amazon.com.au/")
        await page.screenshot(path="before_postcode.png")
        
        try:
            bot_btn = page.locator("button:has-text('Continue shopping'), input[value='Continue shopping']").first
            if await bot_btn.count():
                await bot_btn.click()
                await page.wait_for_timeout(3000)
                
            deliver_btn = page.locator("#glow-ingress-block").first
            await deliver_btn.click()
            await page.wait_for_timeout(2000)
            
            await page.screenshot(path="postcode_popup.png")
            
            with open("popup_dump.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
                
            zip_input = page.locator("#GLUXZipUpdateInput").first
            await zip_input.fill("2000")
            await page.wait_for_timeout(1000)
            
            apply_btn = page.locator("#GLUXZipUpdate input[type='submit'], #GLUXZipUpdate .a-button-input, button:has-text('Apply'), input[aria-labelledby='GLUXZipUpdate-announce']").first
            await apply_btn.click()
            await page.wait_for_timeout(2000)
            
            done_btn = page.locator("button[name='glowDoneButton'], #GLUXConfirmClose, button:has-text('Continue'), button:has-text('Done')").first
            if await done_btn.count():
                await done_btn.click()
                await page.wait_for_timeout(1000)
                
            await page.screenshot(path="after_postcode.png")
                
            print("Dumped HTML")
        except Exception as e:
            print(f"Error: {e}")
            await page.wait_for_timeout(2000)
            
            done_btn = page.locator("button[name='glowDoneButton'], #GLUXConfirmClose").first
            if await done_btn.count():
                await done_btn.click()
                await page.wait_for_timeout(1000)
                
            await page.screenshot(path="after_postcode.png")
            print("Done")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(test_postcode())
