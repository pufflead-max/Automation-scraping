from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json

# Add scraper modules to path
sys.path.insert(0, "/opt/airflow/scraper/src")

from user_credential_manager import UserCredentialManager

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

def rotate_user_nextdoor_cookies(user_email, **context):
    """Log in to Nextdoor directly from DAG and update cookies for a specific user."""
    # If triggered via another DAG for a specific user, only run for that user
    dag_run = context.get('dag_run')
    target_user = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    if target_user and target_user != user_email:
        print(f"⏭️ Skipping rotation for {user_email} as this run is targeted for {target_user}")
        return f"Skipped: Targeted run for {target_user}"

    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    from user_credential_manager import UserCredentialManager
    
    manager = UserCredentialManager()
    creds = manager.get_nextdoor_credentials(user_email)
    
    if not creds or not creds.get("email") or not creds.get("password"):
        print(f"✗ Nextdoor credentials not found for user: {user_email}")
        return f"Failed: No credentials for {user_email}"

    email = creds["email"].strip()
    password = creds["password"].strip()
    
    printable_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
    print(f"🚀 Starting Stealth Nextdoor cookie rotation for User: {user_email} (ND Account: {printable_email})")
    
    with sync_playwright() as p:
        # User-specific browser profile directory
        user_id_clean = user_email.replace('@', '_at_').replace('.', '_')
        user_data_dir = f"/opt/airflow/scraper/cookies/browser_profiles/nextdoor_{user_id_clean}"
        os.makedirs(user_data_dir, exist_ok=True)

        # Fix for "Failed to create a ProcessSingleton" error (more aggressive cleanup)
        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_path = os.path.join(user_data_dir, lock_name)
            if os.path.exists(lock_path) or os.path.islink(lock_path):
                print(f"⚠️ Found stale Chromium lock: {lock_path}. Removing it...")
                try:
                    if os.path.islink(lock_path):
                        os.unlink(lock_path)
                    else:
                        os.remove(lock_path)
                except Exception as e:
                    print(f"Failed to remove lock {lock_name}: {e}")

        launch_args = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ]
        }
        
        if chrome_bin := os.getenv("CHROME_BIN"):
            launch_args["executable_path"] = chrome_bin
        
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ignore_https_errors=True,
            **launch_args
        )
        
        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
        Stealth().apply_stealth_sync(page)
        
        try:
            print("🔍 Checking for existing session...")
            # Increase timeouts for Nextdoor which can be very slow
            navigation_timeout = 60000 
            
            try:
                page.goto("https://nextdoor.com/news_feed/", wait_until="domcontentloaded", timeout=navigation_timeout)
                page.wait_for_timeout(5000) # Give it extra time to settle
                
                if "login" not in page.url.lower() and "signup" not in page.url.lower():
                    print(f"✅ Session still valid for {user_email}! Reusing existing login.")
                else:
                    print(f"🔑 No valid session found for {user_email}. Proceeding to login...")
                    page.goto("https://nextdoor.com/login/", wait_until="domcontentloaded", timeout=navigation_timeout)
            except Exception as e:
                print(f"⚠️ Initial check failed for {user_email}, attempting login anyway: {e}")
                # Ensure we are on the login page if the first visit failed
                try:
                    page.goto("https://nextdoor.com/login/", wait_until="domcontentloaded", timeout=navigation_timeout)
                except Exception as login_goto_error:
                    print(f"❌ Failed to reach login page: {login_goto_error}")
                    raise

            # Detect Bot Challenges Early
            content = page.content()
            if "Verify you are human" in content or "Pardon Our Interruption" in content:
                 print(f"⚠️ Bot challenge detected for {user_email}. Attempting to wait or solve...")
                 page.wait_for_timeout(10000) # Wait a bit to see if it clears
                 page.screenshot(path=f"/opt/airflow/logs/nd_bot_{user_id_clean}_detected.png")

            if "login" in page.url.lower():
                print(f"Filling credentials for {user_email}...")
                email_field = page.locator('input[name="email"], input#id_email').first
                email_field.wait_for(state="visible", timeout=navigation_timeout)
                email_field.fill(email)
                
                password_field = page.locator('input[name="password"], input#id_password').first
                password_field.fill(password)
                
                print("Submitting login form...")
                password_field.press('Enter')
                page.wait_for_timeout(5000)
                
                # Check if still on login page - might need a click
                if "login" in page.url.lower():
                    login_button = page.locator('button[type="submit"], button#signin_button').first
                    if login_button.is_visible():
                        print("Clicking submit button explicitly...")
                        login_button.click(force=True)

            try:
                page.wait_for_url(lambda url: "login" not in url.lower(), timeout=30000)
            except:
                pass
            
            page_text = page.inner_text('body') if page.locator('body').count() > 0 else ""
            if "login code has been sent" in page_text.lower() or "enter login code" in page_text.lower():
                print(f"🔐 2FA EMAIL VERIFICATION DETECTED for {user_email}")
                
                screenshot_path = f"/opt/airflow/logs/nd_2fa_{user_id_clean}.png"
                try:
                    page.screenshot(path=screenshot_path)
                    print(f"📸 Screenshot saved to: {screenshot_path}")
                except:
                    pass
                
                # User-specific 2FA variable
                otp_var_name = f"nextdoor_2fa_code_{user_id_clean}"
                print("="*60)
                print(f"👉 ACTION REQUIRED for user: {user_email}")
                print(f"👉 Nextdoor sent a code to: {printable_email}")
                print(f"👉 Please check email and set Variable: {otp_var_name}")
                print("👉 The DAG will wait for 5 minutes...")
                print("="*60)
                
                Variable.set(otp_var_name, "")
                
                import time
                wait_start = time.time()
                timeout = 600  # Increased to 10 minutes
                otp_code = ""
                
                while time.time() - wait_start < timeout:
                    otp_code = Variable.get(otp_var_name, default_var="").strip()
                    if otp_code and len(otp_code) >= 6:
                        print(f"✅ Received code for {user_email}: {otp_code[:2]}****")
                        break
                    
                    if int(time.time() - wait_start) % 30 == 0:
                        elapsed = int(time.time() - wait_start)
                        rem = timeout - elapsed
                        print(f"User {user_email}: Waiting for code... ({elapsed}s elapsed, {rem}s remaining)")
                    
                    time.sleep(5)
                
                if not otp_code:
                    print(f"❌ Timeout waiting for 2FA code for {user_email}.")
                    raise ValueError(f"2FA required for {user_email} but no code provided via '{otp_var_name}' variable.")
                
                try:
                    code_field = page.locator('input[name="otp_code"], input[name="login_code"], input#id_login_code, input#id_otp_code').first
                    code_field.wait_for(timeout=10000)
                    code_field.fill(otp_code)
                    
                    submit_button = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Submit")').first
                    if submit_button.is_visible():
                        submit_button.click()
                    else:
                        code_field.press('Enter')
                    
                    Variable.set(otp_var_name, "")
                    page.wait_for_url(lambda url: "login" not in url.lower() and "signup" not in url.lower(), timeout=30000)
                except Exception as e:
                    print(f"❌ Error entering 2FA code for {user_email}: {e}")
                    raise
            
            current_url = page.url.lower()
            if "login" not in current_url and ("news_feed" in current_url or "home" in current_url or "feed" in current_url or page.locator('[data-testid="user-profile-menu"]').count() > 0):
                print(f"🎉 Nextdoor login successful for {user_email}! Final URL: {current_url}")
                cookies = browser_context.cookies()
                
                # Save to user-specific cookie file and MongoDB
                manager.save_cookies(user_email, 'nextdoor', cookies)
                
                print(f"✓ Successfully rotated Nextdoor cookies for {user_email}.")
                return "Success"
            else:
                print(f"✗ Nextdoor login failed for {user_email}. Current URL: {current_url}")
                page.screenshot(path=f"/opt/airflow/logs/nd_fail_{user_id_clean}.png")
                raise ValueError(f"Nextdoor login failed for {user_email}. Final URL: {current_url}")
        except Exception as e:
            print(f"✗ Error during Nextdoor rotation for {user_email}: {e}")
            raise
        finally:
            browser_context.close()

with DAG(
    'nextdoor_multi_user_cookie_rotation',
    default_args=default_args,
    description='Dynamic rotation of Nextdoor cookies for multiple users',
    schedule_interval='0 1 */2 * *', # Every 2 days at 1 AM
    catchup=False,
    tags=['maintenance', 'cookies', 'nextdoor', 'multi-user'],
    max_active_runs=1,
) as dag:

    try:
        manager = UserCredentialManager()
        users = manager.get_users_with_credentials('nextdoor')
    except Exception as e:
        print(f"Error fetching users: {e}")
        users = []

    if not users:
        def no_users(): print("No users with Nextdoor credentials found.")
        task = PythonOperator(task_id='no_users_found', python_callable=no_users)
    else:
        for user in users:
            user_email = user['email']
            user_id_clean = user_email.replace('@', '_at_').replace('.', '_')
            
            task = PythonOperator(
                task_id=f'rotate_nd_cookies_{user_id_clean}',
                python_callable=rotate_user_nextdoor_cookies,
                op_kwargs={'user_email': user_email},
                pool='scraper_pool',
            )
