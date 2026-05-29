import asyncio
import os
import time
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import pyotp
import sys

# Load env before importing local modules
load_dotenv()

# Import the shared chrome profile launcher
try:
    from chrome_profile import create_browser
except ImportError:
    print("Error: chrome_profile.py not found. Please run this script from the project root.")
    sys.exit(1)

AMAZON_EMAIL = os.getenv("AMAZON_EMAIL", "")
AMAZON_PASSWORD = os.getenv("AMAZON_PASSWORD", "")
AMAZON_TOTP_SECRET = os.getenv("AMAZON_TOTP_SECRET", "")

async def fill_otp(page):
    """Helper to fill OTP if the screen is present."""
    totp_input = page.locator("input[id='auth-mfa-otpcode']")
    if await totp_input.count() > 0 and await totp_input.is_visible():
        print("   => 2FA requested. Generating TOTP code...")
        if not AMAZON_TOTP_SECRET:
            print("      ERROR: AMAZON_TOTP_SECRET is missing from .env!")
            return False
            
        totp = pyotp.TOTP(AMAZON_TOTP_SECRET)
        current_otp = totp.now()
        print(f"      => Generated OTP: {current_otp}")
        
        await totp_input.fill(current_otp)
        
        remember_device = page.locator("input[name='rememberDevice']")
        if await remember_device.count() > 0:
            print("      => Checking 'Don't require OTP on this browser'...")
            await remember_device.check()
            
        await page.locator("input#auth-signin-button").click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)
        return True
    return False

async def amazon_auto_login(context):
    print("\n--- Starting Amazon Seller Central Auto-Login ---")
    page = await context.new_page()
    
    try:
        print("1. Navigating to Seller Central...")
        await page.goto("https://sellercentral.amazon.in", timeout=60000)
        await page.wait_for_timeout(4000)
        
        # State machine loop: check what screen we are on and handle it
        for step in range(10):  # max 10 steps to prevent infinite loop
            current_url = page.url.lower()
            
            # 1. Are we on the Dashboard?
            # If the screen shows Shudhit, we consider it successfully logged in as per user request
            if "dashboard" in current_url or await page.locator("text='Home'").count() > 0 or await page.get_by_text("Shudhit", exact=False).count() > 0:
                print("=> Reached Amazon Seller Central! 'Shudhit' is visible. You are fully logged in.")
                return True
                
            # 2. Are we on the OTP screen?
            if await fill_otp(page):
                continue

            # 3. Sometimes there's a landing page with a "Log in" button
            if await page.locator("a:has-text('Log in')").count() > 0 and await page.locator("a:has-text('Log in')").first.is_visible():
                print("-> Clicking 'Log in' landing page button...")
                await page.locator("a:has-text('Log in')").first.click()
                await page.wait_for_load_state("networkidle")
                continue

            # 4. Email Form?
            email_input = page.locator("input[type='email'], input[name='email']")
            if await email_input.count() > 0 and await email_input.first.is_visible():
                print(f"-> Filling email: {AMAZON_EMAIL}")
                await email_input.first.fill(AMAZON_EMAIL)
                
                # If there's a continue button (split login), click it
                continue_btn = page.locator("input#continue")
                if await continue_btn.count() > 0 and await continue_btn.first.is_visible():
                    await continue_btn.first.click()
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(2000)
                    continue # Loop around to check for password form
                
            # 5. Password Form?
            pass_input = page.locator("input[type='password'], input[name='password']")
            if await pass_input.count() > 0 and await pass_input.first.is_visible():
                print("-> Filling password...")
                await pass_input.first.fill(AMAZON_PASSWORD)
                
                keep_signed_in = page.locator("input[name='rememberMe']")
                if await keep_signed_in.count() > 0:
                    await keep_signed_in.check()
                    
                print("-> Submitting login...")
                await page.locator("input#signInSubmit").click()
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(3000)
                continue
                
            # If we get here and none of the above matched, we might just need to wait a bit
            await page.wait_for_timeout(3000)
            
        print("\n❌ Error: Could not verify login after 10 steps. Stuck on unknown page.")
        return False

    except Exception as e:
        print(f"\n❌ Error during Amazon auto-login: {e}")
        try:
            await page.wait_for_timeout(30000)
        except Exception:
            pass
        return False
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def main():
    if not AMAZON_EMAIL or not AMAZON_PASSWORD:
        print("Error: AMAZON_EMAIL or AMAZON_PASSWORD missing from .env")
        sys.exit(1)

    async with async_playwright() as p:
        print("Launching persistent Chrome profile...")
        # We don't require Helium here, just need the profile loaded
        context = await create_browser(p, require_helium=False, is_setup_mode=True)
        
        await amazon_auto_login(context)
        
        print("\nClosing browser...")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
