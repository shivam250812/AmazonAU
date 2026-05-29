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

async def amazon_auto_login(context):
    print("\n--- Starting Amazon Seller Central Auto-Login ---")
    page = await context.new_page()
    
    try:
        # Go to Amazon Seller Central
        print("1. Navigating to Seller Central...")
        await page.goto("https://sellercentral.amazon.in", timeout=60000)
        
        # Check if already logged in by looking for dashboard elements
        await page.wait_for_timeout(3000)
        if "dashboard" in page.url.lower() or await page.locator("text='Home'").count() > 0:
            print("=> Already logged in to Amazon Seller Central!")
            return True

        # Need to log in
        print("2. Looking for login form...")
        
        # Sometimes there's a landing page with a "Log in" button
        if await page.locator("a:has-text('Log in')").count() > 0:
            await page.locator("a:has-text('Log in')").first.click()
            await page.wait_for_load_state("networkidle")

        # Fill Email
        email_input = page.locator("input[type='email'], input[name='email']")
        await email_input.wait_for(state="visible", timeout=15000)
        print(f"3. Filling email: {AMAZON_EMAIL}")
        await email_input.fill(AMAZON_EMAIL)
        
        # Click Continue if it exists (Amazon often splits email/password)
        continue_btn = page.locator("input#continue")
        if await continue_btn.count() > 0:
            await continue_btn.click()
            await page.wait_for_load_state("networkidle")

        # Fill Password
        pass_input = page.locator("input[type='password'], input[name='password']")
        await pass_input.wait_for(state="visible", timeout=15000)
        print("4. Filling password...")
        await pass_input.fill(AMAZON_PASSWORD)

        # "Keep me signed in" checkbox
        keep_signed_in = page.locator("input[name='rememberMe']")
        if await keep_signed_in.count() > 0:
            print("5. Checking 'Keep me signed in' box...")
            await keep_signed_in.check()

        # Submit login
        print("6. Submitting login...")
        await page.locator("input#signInSubmit").click()
        await page.wait_for_load_state("networkidle")
        
        # Check for 2FA / TOTP screen
        totp_input = page.locator("input[id='auth-mfa-otpcode']")
        
        try:
            await totp_input.wait_for(state="visible", timeout=10000)
            print("7. 2FA requested. Generating TOTP code...")
            
            if not AMAZON_TOTP_SECRET:
                print("ERROR: AMAZON_TOTP_SECRET is missing from .env!")
                print("Please enter the code manually in the browser window.")
                await page.wait_for_timeout(60000) # Give them a minute
                return False
                
            # Generate the OTP
            totp = pyotp.TOTP(AMAZON_TOTP_SECRET)
            current_otp = totp.now()
            print(f"   => Generated OTP: {current_otp}")
            
            # Fill the OTP
            await totp_input.fill(current_otp)
            
            # Click "Don't require OTP on this browser"
            remember_device = page.locator("input[name='rememberDevice']")
            if await remember_device.count() > 0:
                print("   => Checking 'Don't require OTP on this browser'...")
                await remember_device.check()
                
            # Submit OTP
            await page.locator("input#auth-signin-button").click()
            await page.wait_for_load_state("networkidle")
            
        except Exception:
            print("   (No 2FA screen detected, continuing...)")

        print("8. Waiting to confirm successful login...")
        # Give it a few seconds to load the dashboard
        await page.wait_for_timeout(5000)
        
        print("\n✅ Auto-login complete! The session cookies have been saved to your Chrome profile.")
        print("   You can now run your main scraper script.")
        return True

    except Exception as e:
        print(f"\n❌ Error during Amazon auto-login: {e}")
        print("Please check the browser window and log in manually if needed.")
        await page.wait_for_timeout(60000)
        return False
    finally:
        await page.close()


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
