from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json

# Add scraper modules to path
sys.path.insert(0, "/opt/airflow/scraper/src")

import random
from config import get_proxy_list
from user_credential_manager import UserCredentialManager

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

def rotate_nextdoor_owner_cookies(**context):
    """Log in to Nextdoor for the central owner account and update cookies (Using Playwright)."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    from user_credential_manager import UserCredentialManager
    from config import get_proxy_list
    import random
    
    owner_email = Variable.get("nextdoor_owner_email", default_var=os.getenv("NEXTDOOR_EMAIL"))
    owner_password = Variable.get("nextdoor_owner_password", default_var=os.getenv("NEXTDOOR_PASSWORD"))
    
    if not owner_email or not owner_password:
        print("✗ Central Nextdoor owner credentials not found in Airflow Variables or Env.")
        return "Failed: No owner credentials"

    manager = UserCredentialManager()
    
    printable_email = owner_email[:3] + "***" + owner_email[owner_email.find("@"):] if "@" in owner_email else owner_email[:4] + "***"
    print(f"🚀 Starting Nextdoor cookie rotation for OWNER account: {printable_email} (Using Playwright)")
    
    # ── TEMPORARY: disabled proxy for nextdoor cookie rotation ─────────────
    proxy_override = None
    """
    _proxy_server = os.getenv("PROXY_SERVER")
    _proxy_user   = os.getenv("PROXY_USER")
    _proxy_pass   = os.getenv("PROXY_PASS")
    if _proxy_server and _proxy_user and _proxy_pass:
        proxy_override = {"server": _proxy_server, "username": _proxy_user, "password": _proxy_pass}
        print(f"🌐 Proxy enabled for cookie rotation: {_proxy_server}")
    else:
        proxy_override = None
        print("⚠️  No proxy configured for cookie rotation, proceeding without proxy")
    """
    
    with sync_playwright() as p:
        user_data_dir = f"/opt/airflow/scraper/cookies/browser_profiles/nextdoor_owner"
        os.makedirs(user_data_dir, exist_ok=True)

        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_path = os.path.join(user_data_dir, lock_name)
            if os.path.exists(lock_path) or os.path.islink(lock_path):
                try:
                    if os.path.islink(lock_path): os.unlink(lock_path)
                    else: os.remove(lock_path)
                except: pass

        launch_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        }
        if chrome_bin := os.getenv("CHROME_BIN"): launch_args["executable_path"] = chrome_bin
        
        # Proxy configuration for Playwright
        context_args = {
            "user_data_dir": user_data_dir,
            "viewport": {'width': 1280, 'height': 800},
            "user_agent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            "ignore_https_errors": True,
            **launch_args
        }
        
        if proxy_override:
            server = proxy_override['server']
            # Playwright proxy format: { 'server': 'http://host:port', 'username': 'user', 'password': 'pass' }
            proxy_url = server if '://' in server else f'http://{server}'
            context_args["proxy"] = {
                "server": proxy_url,
                "username": proxy_override['username'],
                "password": proxy_override['password']
            }
            print(f"🌐 Using proxy: {server}")
        
        browser_context = p.chromium.launch_persistent_context(**context_args)
        
        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
        Stealth().apply_stealth_sync(page)
        
        try:
            navigation_timeout = 60000 
            page.goto("https://nextdoor.com/news_feed/", wait_until="domcontentloaded", timeout=navigation_timeout)
            page.wait_for_timeout(5000)
            
            if "login" in page.url.lower() or "signup" in page.url.lower():
                print("🔑 Logging in...")
                page.goto("https://nextdoor.com/login/", wait_until="domcontentloaded", timeout=navigation_timeout)
                page.locator('input[name="email"], input#id_email').first.fill(owner_email)
                password_field = page.locator('input[name="password"], input#id_password').first
                password_field.fill(owner_password)
                password_field.press('Enter')
                page.wait_for_timeout(5000)
                
                # Handle 2FA if needed
                page_text = page.inner_text('body').lower()
                if any(x in page_text for x in ["login code", "enter code", "verification code", "verify your identity"]):
                    two_fa_secret = Variable.get("nextdoor_2fa_secret", default_var=os.getenv("NEXTDOOR_2FA_SECRET"))
                    
                    if two_fa_secret:
                        print("🔐 Generating TOTP code...")
                        import pyotp
                        totp = pyotp.TOTP(two_fa_secret.replace(" ", ""))
                        code = totp.now()
                        
                        inputs = page.locator('input:not([type="hidden"])')
                        if inputs.count() >= 6:
                            for idx, digit in enumerate(code):
                                inputs.nth(idx).fill(digit)
                        else:
                            page.locator('input[name="code"], input[id*="id_code"]').first.fill(code)
                            page.keyboard.press("Enter")
                        page.wait_for_timeout(5000)
                    else:
                        print("🔐 2FA detected. Attempting to fetch OTP from Gmail...")
                        from utils.email_manager import EmailManager
                        email_user = Variable.get("nextdoor_owner_email", default_var=os.getenv("NEXTDOOR_EMAIL"))
                        app_pass = os.getenv("NEXTDOOR_APP_PASSWORD") # Gmail App Password
                        
                        code = None
                        if email_user and app_pass:
                            code = EmailManager.get_nextdoor_otp(email_user, app_pass)
                        
                        if code:
                            print(f"📥 Successfully fetched OTP from Gmail: {code}")
                            inputs = page.locator('input:not([type="hidden"])')
                            if inputs.count() >= 6:
                                for idx, digit in enumerate(code):
                                    inputs.nth(idx).fill(digit)
                            else:
                                page.locator('input[name="code"], input[id*="id_code"]').first.fill(code)
                                page.keyboard.press("Enter")
                            page.wait_for_timeout(5000)
                        else:
                            print("🔐 Email OTP fetch failed. Waiting for manual entry in 'nextdoor_owner_2fa' Airflow variable...")
                            Variable.set("nextdoor_owner_2fa", "WAITING")
                            # Simple poll logic
                            for i in range(30): # Wait 5 minutes max
                                page.wait_for_timeout(10000)
                                manual_code = Variable.get("nextdoor_owner_2fa", default_var="")
                                if manual_code and manual_code != "WAITING":
                                    print(f"📥 Received manual code: {manual_code}")
                                    inputs = page.locator('input:not([type="hidden"])')
                                    if inputs.count() >= 6:
                                        for idx, digit in enumerate(manual_code):
                                            inputs.nth(idx).fill(digit)
                                    else:
                                        page.locator('input[name="code"], input[id*="id_code"]').first.fill(manual_code)
                                        page.keyboard.press("Enter")
                                    break
                
            page.wait_for_url(lambda url: "login" not in url.lower(), timeout=30000)
            cookies = browser_context.cookies()
            print(f"🍪 Retrieved {len(cookies)} cookies.")
            
            manager.save_cookies(owner_email, 'nextdoor', cookies)
            
            # Sync to local JSON file for the scraper
            try:
                cookie_file_path = "/opt/airflow/scraper/cookies/nextdoor_cookies.json"
                os.makedirs(os.path.dirname(cookie_file_path), exist_ok=True)
                with open(cookie_file_path, 'w') as f:
                    json.dump(cookies, f, indent=2)
                print(f"✅ Cookies synced to local file: {cookie_file_path}")
            except Exception as fe:
                print(f"⚠️ Error syncing to local file: {fe}")

            print(f"✅ Successfully rotated Nextdoor cookies for owner {owner_email}.")
            Variable.set("nextdoor_last_rotation", datetime.utcnow().isoformat())
            return "Success"
        except Exception as e:
            print(f"❌ Error during cookie rotation: {e}")
            return f"Failed: {str(e)}"
        finally:
            browser_context.close()

with DAG(
    'nextdoor_owner_cookie_rotation',
    default_args=default_args,
    description='Rotation of Nextdoor cookies for the central owner account',
    schedule_interval=None, # Only triggered by on_failure_callback
    catchup=False,
    tags=['maintenance', 'cookies', 'nextdoor', 'owner'],
    max_active_runs=1,
) as dag:

    rotate_task = PythonOperator(
        task_id='rotate_nextdoor_owner_cookies',
        python_callable=rotate_nextdoor_owner_cookies,
        pool='scraper_pool',
    )
