import os
import asyncio
from playwright.async_api import async_playwright
import sys
from dotenv import load_dotenv

load_dotenv()

HELIUM_EMAIL = os.getenv("HELIUM_EMAIL", "")
HELIUM_PASSWORD = os.getenv("HELIUM_PASSWORD", "")
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
            
            # Wait for dashboard to load
            print("-> Waiting for login to complete...")
            await page.wait_for_timeout(10000)
            
            # Go back to the popup
            print("-> Navigating back to extension popup...")
            await page.goto(popup_url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            
        else:
            print("-> Helium 10 is already logged in!")
            
        # Select the second account
        print("-> Checking account dropdown...")
        
        # Find the dropdown trigger (usually has an SVG arrow down at the bottom right)
        # We look for the container that holds the active account name
        body_text = await page.locator("body").inner_text()
        if "Moin_Khan" in body_text or "Shawal" in body_text:
            print("-> Account selector found. Attempting to click the dropdown button...")
            
            # Click the exact open button based on the HTML dump
            open_btn = page.locator("[data-testid='open-button']")
            
            if await open_btn.count() > 0:
                await open_btn.first.click()
                print("   Clicked open button, waiting for menu...")
                await page.wait_for_timeout(2000)
                
                # Now the menu should be open. Click Moin_Khan.
                moin_khan_btn = page.get_by_text("Moin_Khan", exact=False).last
                if await moin_khan_btn.count() > 0 and await moin_khan_btn.is_visible():
                    print("-> Selecting 'Moin_Khan' (Second account)...")
                    await moin_khan_btn.click()
                    await page.wait_for_timeout(2000)
                else:
                    print("   Could not find 'Moin_Khan' in the dropdown menu.")
            else:
                print("   Could not find the dropdown open button to click.")
        else:
            print("   Account names not found in popup. Might already be selected or UI changed.")

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
