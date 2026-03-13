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

def rotate_nextdoor_owner_cookies(**context):
    """Log in to Nextdoor for the central owner account and update cookies using Playwright."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    from user_credential_manager import UserCredentialManager
    import os
    import json
    from datetime import datetime
    from airflow.models import Variable

    owner_email = Variable.get("nextdoor_owner_email", default_var=os.getenv("NEXTDOOR_EMAIL"))
    owner_password = Variable.get("nextdoor_owner_password", default_var=os.getenv("NEXTDOOR_PASSWORD"))
    
    if not owner_email or not owner_password:
        print("✗ Central Nextdoor owner credentials not found in Airflow Variables or Env.")
        return "Failed: No owner credentials"

    manager = UserCredentialManager()
    printable_email = owner_email[:3] + "***" + owner_email[owner_email.find("@"):] if "@" in owner_email else owner_email[:4] + "***"
    print(f"🚀 Starting Nextdoor cookie rotation for OWNER account: {printable_email} (Using Playwright)")

    with sync_playwright() as p:
        user_data_dir = f"/opt/airflow/scraper/cookies/browser_profiles/nextdoor_owner_playwright"
        os.makedirs(user_data_dir, exist_ok=True)

        # Clear locks to avoid "singleton" error in Docker
        for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_path = os.path.join(user_data_dir, lock)
            if os.path.exists(lock_path) or os.path.islink(lock_path):
                try:
                    if os.path.islink(lock_path): os.unlink(lock_path)
                    else: os.remove(lock_path)
                except: pass

        launch_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        }
        
        # Proxy Configuration
        proxy_server = os.getenv("BRIGHTDATA_PROXY_SERVER")
        proxy_user = os.getenv("BRIGHTDATA_PROXY_USER")
        proxy_pass = os.getenv("BRIGHTDATA_PROXY_PASS")
        
        if proxy_server and proxy_user and proxy_pass:
            print(f"🌐 Configuring Residential Proxy: {proxy_server}")
            launch_args["proxy"] = {
                "server": f"http://{proxy_server}",
                "username": proxy_user,
                "password": proxy_pass
            }

        if chrome_bin := os.getenv("CHROME_BIN"): launch_args["executable_path"] = chrome_bin
        
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
            navigation_timeout = 60000 
            
            # 1. MANDATORY Proxy Health Check
            print("🌐 Verifying proxy connectivity...")
            try:
                # Use a slightly longer timeout for the proxy check
                page.goto("https://api64.ipify.org?format=json", timeout=30000)
                ip_data = page.inner_text('body')
                print(f"📡 Proxy IP Test SUCCESS: {ip_data}")
            except Exception as ip_err:
                print(f"❌ PROXY FAILURE: Could not connect to the internet via Bright Data. Error: {ip_err}")
                screenshot_path = f"/opt/airflow/scraper/cookies/proxy_fail_{datetime.now().strftime('%H%M%S')}.png"
                try: page.screenshot(path=screenshot_path)
                except: pass
                return f"Failed: Proxy Connectivity Error - {str(ip_err)}"

            print("🔗 Navigating to Nextdoor...")
            # Try a different URL or the root domain first to warm up the proxy connection
            try:
                print("🚀 Attempting root domain navigation...")
                page.goto("https://nextdoor.com/", wait_until="commit", timeout=navigation_timeout)
            except Exception as root_err:
                print(f"⚠️ Root domain navigation failed: {root_err}. Continuing to news_feed...")

            response = page.goto("https://nextdoor.com/news_feed/", wait_until="domcontentloaded", timeout=navigation_timeout)
            page.wait_for_timeout(5000)
            
            current_url = page.url.lower()
            if "login" in current_url or "signup" in current_url or "identify" in page.content().lower():
                print("🔑 Login required.")
                if "login" not in current_url:
                    page.goto("https://nextdoor.com/login/", wait_until="domcontentloaded", timeout=navigation_timeout)
                
                page.locator('input[name="email"], input#id_email').first.fill(owner_email)
                password_field = page.locator('input[name="password"], input#id_password').first
                password_field.fill(owner_password)
                password_field.press('Enter')
                page.wait_for_timeout(8000)
                
                # Handle 2FA
                page_text = page.inner_text('body').lower()
                if any(x in page_text for x in ["login code", "enter code", "verification code", "verify your identity"]):
                    print("🔐 2FA detected!")
                    two_fa_secret = Variable.get("nextdoor_2fa_secret", default_var=os.getenv("NEXTDOOR_2FA_SECRET"))
                    
                    code = None
                    if two_fa_secret:
                        import pyotp
                        code = pyotp.TOTP(two_fa_secret.replace(" ", "")).now()
                    else:
                        from utils.email_manager import EmailManager
                        app_pass = os.getenv("NEXTDOOR_APP_PASSWORD")
                        code = EmailManager.get_nextdoor_otp(owner_email, app_pass) if app_pass else None
                        
                        if not code:
                            print("🔐 Waiting for manual code in 'nextdoor_owner_2fa' Airflow variable...")
                            Variable.set("nextdoor_owner_2fa", "WAITING")
                            for _ in range(30):
                                page.wait_for_timeout(10000)
                                manual_code = Variable.get("nextdoor_owner_2fa", default_var="")
                                if manual_code and manual_code != "WAITING":
                                    code = manual_code
                                    break
                    
                    if code:
                        page.locator('input[name="code"], input[id*="id_code"]').first.fill(code)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(8000)

            # Verification and Cookie Capture
            page.wait_for_url(lambda url: "login" not in url.lower(), timeout=30000)
            cookies = browser_context.cookies()
            print(f"🍪 Retrieved {len(cookies)} cookies.")
            
            manager.save_cookies(owner_email, 'nextdoor', cookies)
            
            # Sync to local JSON file
            try:
                cookie_file_path = "/opt/airflow/scraper/cookies/nextdoor_cookies.json"
                os.makedirs(os.path.dirname(cookie_file_path), exist_ok=True)
                with open(cookie_file_path, 'w') as f:
                    json.dump(cookies, f, indent=2)
                print(f"✅ Cookies synced to local file: {cookie_file_path}")
                print(f"📄 Saved File Content: {json.dumps(cookies, indent=2)}")
            except Exception as fe:
                print(f"⚠️ Error syncing to local file: {fe}")

            print(f"✅ Successfully rotated Nextdoor cookies for {owner_email}.")
            Variable.set("nextdoor_last_rotation", datetime.utcnow().isoformat())
            return "Success"
        except Exception as e:
            print(f"❌ Error during rotation: {e}")
            screenshot_path = f"/opt/airflow/scraper/cookies/nd_error_{datetime.now().strftime('%H%M%S')}.png"
            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
            try: page.screenshot(path=screenshot_path)
            except: pass
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
