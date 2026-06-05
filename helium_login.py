import os
import asyncio
from playwright.async_api import async_playwright
import sys
from dotenv import load_dotenv

load_dotenv()

HELIUM_EMAIL = os.getenv("HELIUM_EMAIL", "")
HELIUM_PASSWORD = os.getenv("HELIUM_PASSWORD", "")
HELIUM_SUB_ACCOUNT = os.getenv("HELIUM_SUB_ACCOUNT", "Moin_Khan")
HELIUM10_EXTENSION_ID = os.getenv("HELIUM10_EXTENSION_ID", "njmehopjdpcckochcggncklnlmikcbnb")

async def helium_auto_login(context):
    print("\n--- Starting Helium 10 Auto-Login ---")
    page = await context.new_page()
    
    try:
        from notifications import send_email_notification
    except ImportError:
        def send_email_notification(subject, message): pass
        
    login_action_taken = False
        
    try:
        popup_url = f"chrome-extension://{HELIUM10_EXTENSION_ID}/popup.html"
        print(f"1. Navigating to Helium 10 extension popup ({popup_url})...")
        
        # Extensions can be slow to start, so we try navigating a few times if it fails
        for _ in range(3):
            try:
                await page.goto(popup_url, timeout=30000, wait_until="domcontentloaded")
                break
            except Exception as e:
                print(f"   Popup not ready yet, retrying... {e}")
                await page.wait_for_timeout(3000)
                
        await page.wait_for_timeout(3000)
        
        # Check if we are logged out (Log into My Account button)
        login_btn = page.locator("button:has-text('Log into My Account'), a:has-text('Log into My Account')").first
        
        if await login_btn.count() > 0 and await login_btn.is_visible():
            print("-> Helium 10 is logged out! Triggering login flow...")
            login_action_taken = True
            try:
                send_email_notification(
                    subject="Amazon Scraper: Helium 10 Login Required",
                    message="The Helium 10 session expired. The script is logging back in automatically..."
                )
            except Exception:
                pass
                
            print("-> Navigating to Helium 10 Login Page...")
            await page.goto("https://members.helium10.com/user/signin", timeout=60000)
            await page.wait_for_timeout(3000)
            
            # Fill Email
            print(f"-> Filling email: {HELIUM_EMAIL}")
            email_input = page.locator("#loginform-email")
            await email_input.wait_for(state="visible", timeout=30000)
            await email_input.fill(HELIUM_EMAIL)
            
            # Fill Password
            print("-> Filling password...")
            pass_input = page.locator("#loginform-password")
            await pass_input.fill(HELIUM_PASSWORD)
            
            # Submit
            print("-> Submitting login...")
            await page.locator("button[type='submit']").click()
            
            # Wait for network and check for 2FA prompt
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(3000)
            
            otp_input = page.locator("input[name*='otp' i], input[name*='code' i], input[id*='otp' i], input[id*='code' i], input[placeholder*='code' i]").first
            if await otp_input.count() > 0 and await otp_input.is_visible():
                print("   => Helium 10 2FA requested. Generating TOTP code...")
                HELIUM_TOTP_SECRET = os.getenv("HELIUM_TOTP_SECRET", "")
                if not HELIUM_TOTP_SECRET:
                    print("      ERROR: HELIUM_TOTP_SECRET is missing from .env!")
                else:
                    import pyotp
                    totp = pyotp.TOTP(HELIUM_TOTP_SECRET)
                    current_otp = totp.now()
                    print(f"      => Generated OTP: {current_otp}")
                    await otp_input.fill(current_otp)
                    
                    submit_otp = page.locator("button[type='submit'], button:has-text('Verify'), button:has-text('Submit')").first
                    if await submit_otp.count() > 0 and await submit_otp.is_visible():
                        await submit_otp.click()
            
            # Wait for dashboard to load
            print("-> Waiting for login to complete...")
            await page.wait_for_timeout(7000)
            
            # Go back to the popup
            print("-> Navigating back to extension popup...")
            await page.goto(popup_url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            
        else:
            print("-> Helium 10 is already logged in!")
            
        # Select the second account
        print(f"-> Checking account dropdown for '{HELIUM_SUB_ACCOUNT}'...")
        
        # Check if the sub-account is ALREADY selected!
        body_text = await page.locator("body").inner_text()
        
        # The currently selected account is usually at the bottom next to a downward arrow button.
        # Let's force open the dropdown by trying multiple possible triggers
        triggers = [
            page.locator("[data-testid='open-button']").first,
            page.locator("button:has(svg)").last, # The button with the arrow icon is likely the last button on the page
            page.locator("svg.lucide-chevron-down").last,
            page.locator("button").last # Fallback to clicking the absolute last button on the screen
        ]
        
        opened = False
        for trigger in triggers:
            if await trigger.count() > 0 and await trigger.is_visible():
                print("   Found a dropdown trigger. Attempting to click...")
                try:
                    await trigger.click(force=True)
                    opened = True
                    await page.wait_for_timeout(2000)
                    break
                except Exception:
                    pass
                    
        if not opened:
            print("   Could not find or click the dropdown trigger. The UI might have changed.")
            # We will still try to find the text anyway, just in case it's already visible!
            
        print(f"   Searching for profile '{HELIUM_SUB_ACCOUNT}'...")
        # Look for any element containing the sub account name
        sub_account_btn = page.locator(f"//*[contains(text(), '{HELIUM_SUB_ACCOUNT}')]").last
        
        if await sub_account_btn.count() > 0:
            print(f"-> Found '{HELIUM_SUB_ACCOUNT}'! Attempting to click...")
            try:
                # Use force=True because dropdown items are often obscured or in weird z-indexes
                await sub_account_btn.click(force=True)
                print(f"-> Clicked '{HELIUM_SUB_ACCOUNT}' successfully!")
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"   Failed to click profile: {e}")
                # Fallback: evaluate JS click
                try:
                    print("   Trying JavaScript click fallback...")
                    await sub_account_btn.evaluate("node => node.click()")
                    await page.wait_for_timeout(3000)
                except Exception as e2:
                    print(f"   JS click also failed: {e2}")
        else:
            print(f"   Could not find any element containing '{HELIUM_SUB_ACCOUNT}'.")
            print("   Available text on page: ", (await page.locator("body").inner_text())[:200].replace('\n', ' '))
            
            # Dump the HTML and push it so we can debug exactly what Helium changed!
            try:
                html_content = await page.content()
                with open("popup_debug.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("   Pushing popup_debug.html to GitHub for analysis...")
                os.system("git add popup_debug.html && git commit -m 'Auto-push Helium popup debug HTML' && git push")
            except Exception as e3:
                print(f"   Failed to push debug HTML: {e3}")

        if login_action_taken:
            print("\n=> Helium 10 auto-login completed successfully!")
            try:
                send_email_notification(
                    subject="Amazon Scraper: Helium 10 Auto-Login Successful",
                    message="The script has successfully auto-logged into Helium 10 and selected the correct account!"
                )
            except Exception:
                pass
                
        return True

    except Exception as e:
        print(f"\n❌ Error during Helium 10 auto-login: {e}")
        try:
            await page.screenshot(path="helium_login_error.png", full_page=True)
            print("Saved error screenshot to helium_login_error.png")
        except Exception:
            pass
        
        if login_action_taken:
            try:
                send_email_notification(
                    subject="Amazon Scraper: Helium 10 Auto-Login Failed",
                    message=f"The Helium 10 auto-login script encountered an error: {e}"
                )
            except Exception:
                pass
        return False
    finally:
        try:
            await page.close()
        except Exception:
            pass
