import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# Load environment variables
load_dotenv()

def test_nextdoor_rotation():
    owner_email = os.getenv("NEXTDOOR_EMAIL")
    owner_password = os.getenv("NEXTDOOR_PASSWORD")

    proxy_server = os.getenv("BRIGHTDATA_PROXY_SERVER")
    proxy_user = os.getenv("BRIGHTDATA_PROXY_USER")
    proxy_pass = os.getenv("BRIGHTDATA_PROXY_PASS")

    # Virtual Display for headed mode in Docker
    display = None
    is_headless = os.getenv("NEXTDOOR_HEADLESS", "false").lower() == "true"

    if not is_headless:
        from pyvirtualdisplay import Display
        print(" Starting Virtual Display (Xvfb)...")
        display = Display(visible=0, size=(1280, 800))
        display.start()

    print(f" Starting Standalone Nextdoor Test for: {owner_email}")

    with sync_playwright() as p:
        launch_args = {
            "headless": is_headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        }

        # Use existing Chrome binary if available in container
        if chrome_bin := os.getenv("CHROME_BIN"):
            print(f" Using browser executable: {chrome_bin}")
            launch_args["executable_path"] = chrome_bin

        if proxy_server:
            print(f" Using Proxy: {proxy_server}")
            launch_args["proxy"] = {
                "server": f"http://{proxy_server}",
                "username": proxy_user,
                "password": proxy_pass
            }

        browser = p.chromium.launch(**launch_args)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
            ignore_https_errors=True,
            color_scheme='dark'
        )

        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        try:
            # 1. Check IP
            print(" Verifying Connection...")
            page.goto("https://api64.ipify.org?format=json", timeout=30000)
            print(f" Current IP: {page.inner_text('body')}")

            # 2. Go to Nextdoor
            print(" Navigating to Nextdoor...")
            page.goto("https://nextdoor.com/news_feed/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            print(f" Current URL: {page.url}")

            if "login" in page.url.lower():
                print(" Login required. Entering credentials...")
                page.locator('input[name="email"], input#id_email').first.fill(owner_email)
                page.locator('input[name="password"], input#id_password').first.fill(owner_password)
                page.keyboard.press("Enter")

                print(" Waiting for login/2FA...")
                page.wait_for_timeout(10000)

                # Check for 2FA
                if "code" in page.content().lower() or "verify" in page.content().lower():
                    print(" 2FA screen detected! Please check your email/app.")
                    # In a test script, we wait for you to potentially handle it or just fail
                    page.screenshot(path="nd_2fa_detected.png")
                    print(" Screenshot nd_2fa_detected.png saved.")

            # 3. Final Verification
            cookies = context.cookies()
            has_session = any(c['name'] == 'ndbr_at' for c in cookies)

            print(f" Retrieved {len(cookies)} cookies.")
            if has_session:
                print(" Login SUCCESS! ndbr_at cookie found.")
            else:
                print(" Login FAILED: No ndbr_at cookie.")
                page.screenshot(path="nd_test_fail.png")

            # Output cookies to file
            with open("test_cookies.json", "w") as f:
                json.dump(cookies, f, indent=2)
            print(" All cookies saved to test_cookies.json")

        except Exception as e:
            print(f" Error during test: {e}")
            import traceback
            traceback.print_exc()
            if 'page' in locals():
                try:
                    page.screenshot(path="nd_test_error.png")
                    print(" Saved nd_test_error.png")
                except Exception as ss_err:
                    print(f" Could not save screenshot: {ss_err}")
        finally:
            if 'browser' in locals():
                try: browser.close()
                except: pass
            if display:
                try: display.stop()
                except: pass

if __name__ == "__main__":
    test_nextdoor_rotation()
