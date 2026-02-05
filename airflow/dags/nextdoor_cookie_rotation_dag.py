from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json

# Add scraper modules to path
sys.path.insert(0, "/opt/airflow/scraper/src")

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

def rotate_nextdoor_cookies(**context):
    """Log in to Nextdoor directly from DAG and update cookies in Airflow Variable."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    
    # These are now initialized from .env -> variables.json -> Airflow Variable at startup
    email = Variable.get("nextdoor_email", default_var="ENTER_YOUR_EMAIL").strip()
    password = Variable.get("nextdoor_password", default_var="ENTER_YOUR_PASSWORD").strip()
    
    if email == "ENTER_YOUR_EMAIL" or password == "ENTER_YOUR_PASSWORD":
        print("✗ Nextdoor credentials are not set in Airflow Variables.")
        raise ValueError("Nextdoor credentials missing or unconfigured.")
    
    printable_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
    print(f"Starting Stealth Nextdoor cookie rotation for {printable_email}")
    
    with sync_playwright() as p:
        # Browser profile directory (MUST be persistent to bypass 2FA)
        user_data_dir = "/opt/airflow/scraper/browser_profiles/nextdoor"
        os.makedirs(user_data_dir, exist_ok=True)

        launch_args = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled", # Hide automation flag
                "--disable-infobars",
            ]
        }
        
        if chrome_bin := os.getenv("CHROME_BIN"):
            launch_args["executable_path"] = chrome_bin
        
        # Launch with PERSISTENT context (this is the key to bypass 2FA)
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ignore_https_errors=True,
            **launch_args
        )
        
        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
        Stealth().apply_stealth_sync(page) # Apply stealth evasions
        
        try:
            # STEP 1: Check if already logged in! (Bypasses login completely if session is valid)
            print("🔍 Checking for existing session...")
            try:
                page.goto("https://nextdoor.com/news_feed/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                if "login" not in page.url.lower() and "signup" not in page.url.lower():
                    print("✅ Session still valid! Resusing existing login.")
                else:
                    print("🔑 No valid session found. Proceeding to login...")
                    page.goto("https://nextdoor.com/login/", wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"Initial check failed, attempting login anyway: {e}")
                page.goto("https://nextdoor.com/login/", wait_until="domcontentloaded", timeout=60000)

            # Check for bot detection before we even start
            if "Verify you are human" in page.content() or "Pardon Our Interruption" in page.content():
                 print("✗ Bot challenge detected on landing. Saving screenshot...")
                 page.screenshot(path="/opt/airflow/logs/nextdoor_bot_landing.png")

            # Fill Login Form if on login page
            if "login" in page.url.lower():
                print("Filling credentials...")
                email_field = page.locator('input[name="email"], input#id_email').first
                email_field.wait_for(timeout=10000)
                email_field.fill(email)
                
                password_field = page.locator('input[name="password"], input#id_password').first
                password_field.fill(password)
                
                print("Submitting login form...")
                # Multiple submission attempts for stability
                password_field.press('Enter')
                page.wait_for_timeout(2000)
                
                if "login" in page.url.lower():
                    login_button = page.locator('button[type="submit"]').first
                    if login_button.is_visible():
                        login_button.click(force=True)

            # Wait for result
            try:
                page.wait_for_url(lambda url: "login" not in url.lower(), timeout=30000)
            except:
                pass
            
            # Check for 2FA email verification challenge
            page_text = page.inner_text('body') if page.locator('body').count() > 0 else ""
            if "login code has been sent" in page_text.lower() or "enter login code" in page_text.lower():
                print("🔐 2FA EMAIL VERIFICATION DETECTED")
                
                # Save a screenshot to help the user see where to enter
                screenshot_path = "/opt/airflow/logs/nextdoor_2fa_challenge.png"
                try:
                    page.screenshot(path=screenshot_path)
                    print(f"📸 Screenshot saved to: {screenshot_path}")
                except:
                    pass
                
                print("="*60)
                print("👉 ACTION REQUIRED: Nextdoor sent a code to your email.")
                print("👉 Please check your email and set the result in Airflow Variables.")
                print("👉 KEY: nextdoor_2fa_code")
                print("👉 The DAG will wait for 5 minutes...")
                print("="*60)
                
                # Clear any old code first
                Variable.set("nextdoor_2fa_code", "")
                
                import time
                wait_start = time.time()
                # Check for 2FA email verification challenge
                page_text = page.inner_text('body').lower()
                if "login code has been sent" in page_text or "enter login code" in page_text:
                    print("🔐 2FA EMAIL VERIFICATION DETECTED")
                    
                    # Save a screenshot to help the user see where to enter
                    screenshot_path = "/opt/airflow/logs/nextdoor_2fa_challenge.png"
                    try:
                        page.screenshot(path=screenshot_path)
                        print(f"📸 Screenshot saved to: {screenshot_path}")
                    except:
                        pass
                    
                    print("="*60)
                    print("👉 ACTION REQUIRED: Nextdoor sent a code to your email.")
                    print("👉 Please check your email and set the result in Airflow Variables.")
                    print("👉 KEY: nextdoor_2fa_code")
                    print("👉 The DAG will wait for 5 minutes...")
                    print("="*60)
                    
                    # Clear any old code first
                    Variable.set("nextdoor_2fa_code", "")
                    
                    import time
                    wait_start = time.time()
                    timeout = 300 # 5 minutes
                    otp_code = ""
                    
                    while time.time() - wait_start < timeout:
                        otp_code = Variable.get("nextdoor_2fa_code", default_var="").strip()
                        if otp_code and len(otp_code) >= 6:
                            print(f"✅ Received code: {otp_code[:2]}****")
                            break
                        
                        if int(time.time() - wait_start) % 30 == 0:
                            elapsed = int(time.time() - wait_start)
                            print(f"Still waiting for code... ({elapsed}s elapsed)")
                        
                        time.sleep(5)
                    
                    if not otp_code:
                        print("❌ Timeout waiting for 2FA code.")
                        raise ValueError("2FA email verification required but no code provided via 'nextdoor_2fa_code' variable.")
                    
                    # Try to fill the code
                    try:
                        code_field = page.locator('input[name="otp_code"], input[name="login_code"], input#id_login_code, input#id_otp_code').first
                        code_field.wait_for(timeout=10000)
                        code_field.fill(otp_code)
                        print("Filled 2FA code")
                        
                        # Click submit or press enter
                        submit_button = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Submit")').first
                        if submit_button.is_visible():
                            submit_button.click()
                        else:
                            code_field.press('Enter')
                        
                        print("Submitted 2FA form")
                        
                        # Clear the variable now that it's used
                        Variable.set("nextdoor_2fa_code", "")
                        
                        # Wait for news feed
                        page.wait_for_url(lambda url: "login" not in url.lower() and "signup" not in url.lower(), timeout=30000)
                    except Exception as e:
                        print(f"❌ Error entering/submitting 2FA code: {e}")
                        raise
            
            # Final check - are we on the feed?
            current_url = page.url.lower()
            if "login" not in current_url and ("news_feed" in current_url or "home" in current_url or "feed" in current_url or page.locator('[data-testid="user-profile-menu"]').count() > 0):
                print(f"🎉 Nextdoor login successful! Final URL: {current_url}")
                cookies = browser_context.cookies()
                
                # Update Airflow Variable
                Variable.set("nextdoor_cookies", json.dumps(cookies))
                
                # Also save to local file for scraper fallback
                cookie_file = "/opt/airflow/scraper/cookies/nextdoor_cookies.json"
                os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
                with open(cookie_file, 'w') as f:
                    json.dump(cookies, f, indent=2)
                
                print("✓ Successfully rotated Nextdoor cookies and saved browser state.")
                return "Success"
            else:
                print(f"✗ Nextdoor login failed. Current URL: {current_url}")
                page.screenshot(path="/opt/airflow/logs/nextdoor_login_failure.png")
                raise ValueError(f"Nextdoor login failed. Final URL: {current_url}")
        except Exception as e:
            print(f"✗ Error during Nextdoor rotation: {e}")
            raise
        finally:
            browser_context.close()

with DAG(
    'nextdoor_cookie_rotation_dag',
    default_args=default_args,
    description='Rotation of Nextdoor scraper cookies',
    schedule_interval='0 0 */2 * *', # Every 2 days at midnight
    catchup=False,
    tags=['maintenance', 'cookies', 'nextdoor'],
) as dag:

    nd_rotation = PythonOperator(
        task_id='rotate_nextdoor_cookies',
        python_callable=rotate_nextdoor_cookies,
    )
