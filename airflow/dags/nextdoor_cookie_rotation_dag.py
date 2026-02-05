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
    
    # These are now initialized from .env -> variables.json -> Airflow Variable at startup
    email = Variable.get("nextdoor_email", default_var="ENTER_YOUR_EMAIL").strip()
    password = Variable.get("nextdoor_password", default_var="ENTER_YOUR_PASSWORD").strip()
    
    if email == "ENTER_YOUR_EMAIL" or password == "ENTER_YOUR_PASSWORD":
        print("✗ Nextdoor credentials are not set in Airflow Variables.")
        print("👉 Please update them in the Airflow UI or your .env file and restart.")
        raise ValueError("Nextdoor credentials missing or unconfigured.")
    
    printable_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
    print(f"Starting Nextdoor cookie rotation for {printable_email}")
    
    with sync_playwright() as p:
        launch_args = {"headless": True}
        if chrome_bin := os.getenv("CHROME_BIN"):
            launch_args.update({"executable_path": chrome_bin, "args": ["--no-sandbox", "--disable-dev-shm-usage"]})
        
        browser = p.chromium.launch(**launch_args)
        browser_context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = browser_context.new_page()
        
        try:
            print(f"Navigating to login page for {email}...")
            # Use 'domcontentloaded' instead of 'networkidle' to avoid timeouts on slow connections/tracking scripts
            try:
                page.goto("https://nextdoor.com/login/", wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"Initial navigation warning: {e}. Attempting to proceed...")
            
            # Check for actual bot detection challenges (not just meta tags)
            # Look for visible CAPTCHA iframes or challenge text in the body
            page_text = page.inner_text('body') if page.locator('body').count() > 0 else ""
            has_captcha_iframe = page.locator('iframe[src*="captcha"], iframe[src*="hcaptcha"], iframe[src*="recaptcha"]').count() > 0
            has_challenge_text = "Verify you are human" in page_text or "Pardon Our Interruption" in page_text or "Security check" in page_text
            
            if has_captcha_iframe or has_challenge_text:
                print("✗ Bot detection triggered (CAPTCHA or security challenge detected).")
                print(f"Page text snippet: {page_text[:500]}")
                raise ValueError("Anti-bot wall detected. Cannot proceed with automatic rotation.")

            # Wait for email field specifically - this confirms we are on the right page
            print("Checking for login form...")
            email_field = page.locator('input[name="email"], input#id_email').first
            email_field.wait_for(timeout=20000)
            
            # Clear and fill email
            email_field.click()
            email_field.fill('')  # Clear first
            page.wait_for_timeout(500)
            email_field.type(email, delay=100)
            print(f"Filled email field")
            
            # Fill password with human-like delay
            password_field = page.locator('input[name="password"], input#id_password').first
            password_field.click()
            password_field.fill('')  # Clear first
            page.wait_for_timeout(500)
            password_field.type(password, delay=100)
            print(f"Filled password field")
            
            # Wait a moment for any client-side validation
            page.wait_for_timeout(1000)
            
            # Check for immediate error messages (e.g., "Invalid email format")
            immediate_error = page.locator('.error-message, [role="alert"], .alert-danger, #id_errors, .FormErrorText').first
            if immediate_error.is_visible():
                error_text = immediate_error.inner_text()
                print(f"✗ Form validation error: {error_text}")
                raise ValueError(f"Login form validation failed: {error_text}")
            
            # Submit the form - try button click first, then Enter key as fallback
            print("Submitting login form...")
            login_button = page.locator('button[type="submit"], button#signin_button').first
            if login_button.is_visible():
                login_button.click()
                print("Clicked login button")
            else:
                # Fallback: press Enter on password field
                password_field.press('Enter')
                print("Pressed Enter on password field")
            
            # Wait for navigation or a change in URL
            print("Waiting for navigation after login...")
            try:
                # Wait for either the dashboard/newsfeed or a known error state
                page.wait_for_url(lambda url: "login" not in url.lower() and "signup" not in url.lower(), timeout=30000)
            except Exception:
                print("Navigation timeout - checking page state...")
                print(f"Current URL: {page.url}")
                print(f"Page Title: {page.title()}")
                
                # Debug: Check if form fields still have values (might indicate form wasn't submitted)
                try:
                    email_value = page.locator('input[name="email"], input#id_email').first.input_value()
                    has_email = len(email_value) > 0
                    print(f"Email field has value: {has_email}")
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

            # Check for common error messages with expanded selectors
            error_selectors = [
                '.error-message', 
                '[role="alert"]', 
                '.alert-danger', 
                '#id_errors', 
                '.FormErrorText',
                '.AuthenticationError',
                '.signin-error',
                '[data-testid="error-message"]'
            ]
            error_found = False
            for selector in error_selectors:
                error_feedback = page.locator(selector).first
                if error_feedback.is_visible():
                    error_text = error_feedback.inner_text()
                    print(f"✗ Nextdoor login error detected ({selector}): {error_text}")
                    error_found = True
            
            # Check if logged in (url shouldn't contain login/signup)
            current_url = page.url.lower()
            if "login" not in current_url and "signup" not in current_url and "news_feed" in current_url or "nextdoor.com/home" in current_url or "nextdoor.com/feed" in current_url:
                print(f"Nextdoor login successful! Final URL: {current_url}")
                cookies = browser_context.cookies()
                
                # Update Airflow Variable
                Variable.set("nextdoor_cookies", json.dumps(cookies))
                
                # Also save to local file for scraper fallback
                cookie_file = "/opt/airflow/scraper/cookies/nextdoor_cookies.json"
                os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
                with open(cookie_file, 'w') as f:
                    json.dump(cookies, f, indent=2)
                
                print("✓ Successfully rotated Nextdoor cookies.")
                return "Success"
            else:
                # One last check: maybe we are logged in but URL still has login (unlikely but...)
                # Check for profile icon or news feed elements
                if page.locator('[data-testid="user-profile-menu"], .user-profile-menu').is_visible():
                     print("✓ Detected logged-in state via UI elements despite URL.")
                     cookies = browser_context.cookies()
                     Variable.set("nextdoor_cookies", json.dumps(cookies))
                     return "Success"
                     
                print(f"✗ Nextdoor login failed. Current URL: {current_url}")
                # Log some of the page text to help debug
                try:
                    body_text = page.inner_text('body')
                    print(f"Page snippet: {body_text[:500]}...")
                except:
                    pass
                raise ValueError(f"Nextdoor login failed. Current URL: {current_url}")
        except Exception as e:
            print(f"✗ Error during Nextdoor rotation: {e}")
            raise
        finally:
            browser.close()

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
