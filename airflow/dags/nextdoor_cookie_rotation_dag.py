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
    """Log in to Nextdoor for the central owner account and update cookies using Selenium."""
    import os
    import time
    import json
    import zipfile
    from datetime import datetime
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from user_credential_manager import UserCredentialManager
    
    owner_email = Variable.get("nextdoor_owner_email", default_var=os.getenv("NEXTDOOR_EMAIL"))
    owner_password = Variable.get("nextdoor_owner_password", default_var=os.getenv("NEXTDOOR_PASSWORD"))
    
    if not owner_email or not owner_password:
        print("✗ Central Nextdoor owner credentials not found in Airflow Variables or Env.")
        return "Failed: No owner credentials"

    manager = UserCredentialManager()
    
    print(f"🚀 Starting Nextdoor cookie rotation for OWNER account: {owner_email} (Using Selenium)")
    
    use_xvfb = Variable.get("nextdoor_use_xvfb", default_var="true").lower() == "true"
    display = None
    if use_xvfb:
        from pyvirtualdisplay import Display
        print("🖥️ Starting Virtual Display (Xvfb)...")
        display = Display(visible=0, size=(1280, 800))
        display.start()

    chrome_options = Options()
    if not use_xvfb:
        chrome_options.add_argument("--headless=new")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    user_data_dir = f"/opt/airflow/scraper/cookies/browser_profiles/nextdoor_owner_selenium"
    os.makedirs(user_data_dir, exist_ok=True)
    # Clear locks
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = os.path.join(user_data_dir, lock)
        if os.path.exists(lock_path):
            try: os.remove(lock_path)
            except: pass
            
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    # Proxy Configuration with Authentication support via Extension
    proxy_server = os.getenv("BRIGHTDATA_PROXY_SERVER")
    proxy_user = os.getenv("BRIGHTDATA_PROXY_USER")
    proxy_pass = os.getenv("BRIGHTDATA_PROXY_PASS")

    if proxy_server and proxy_user and proxy_pass:
        print(f"🌐 Configuring Residential Proxy: {proxy_server}")

        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy Auth",
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
            "background": {"scripts": ["background.js"], "persistent": true},
            "minimum_chrome_version":"22.0.0"
        }
        """

        background_js = f"""
        chrome.webRequest.onAuthRequired.addListener(
            function(details) {{
                return {{
                    authCredentials: {{
                        username: "{proxy_user}",
                        password: "{proxy_pass}"
                    }}
                }};
            }},
            {{urls: ["<all_urls>"]}},
            ["blocking"]
        );
        """
        
        plugin_file = os.path.join(user_data_dir, 'proxy_auth_final.zip')
        with zipfile.ZipFile(plugin_file, 'w') as zp:
            zp.writestr("manifest.json", manifest_json)
            zp.writestr("background.js", background_js)
        
        chrome_options.add_extension(plugin_file)
        chrome_options.add_argument(f"--proxy-server=http://{proxy_server}")
        print(f"📦 Proxy Auth Extension active at: {plugin_file}")

    # Critical for Bright Data and Headless reliability
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-web-security")
    
    chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    if chrome_bin:
        chrome_options.binary_location = chrome_bin

    service = Service(executable_path=os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver"))
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        wait = WebDriverWait(driver, 60)
        
        # IP Diagnostic
        print("🔍 Checking outbound IP address...")
        try:
            # checkip.amazonaws.com returns plain text
            driver.get("http://checkip.amazonaws.com")
            time.sleep(5)
            ip_info = driver.find_element(By.TAG_NAME, 'body').text.strip()
            print(f"📡 Current Outbound IP: {ip_info}")
        except Exception as ip_err:
            print(f"⚠️ Could not verify IP: {ip_err}")
            print(f"📄 Page Source Sneak Peak (IP Check): {driver.page_source[:200]}")

        print("🔗 Navigating to Nextdoor...")
        driver.get("https://nextdoor.com/news_feed/")
        time.sleep(12) # Increased wait for proxy/DNS
        
        page_source = driver.page_source.lower()
        current_url = driver.current_url.lower()
        page_title = driver.title
        print(f"📍 Initial Page Title: '{page_title}' | URL: {current_url}")

        # Check for Proxy/KYC issues early
        if any(x in page_source for x in ["brightdata", "kyc", "bad_endpoint", "住宅受限"]):
            print("❌ Proxy block detected (Bright Data KYC required).")
            driver.save_screenshot(f"/opt/airflow/scraper/cookies/proxy_block_{datetime.now().strftime('%H%M%S')}.png")
            return "Failed: Proxy KYC block"

        if "login" in current_url or "signup" in current_url or "welcome back" in page_source:
            print("🔑 Login page detected.")
            driver.get("https://nextdoor.com/login/")
            
            # Re-check for rate limit on login page
            time.sleep(5)
            page_text = driver.find_element(By.TAG_NAME, 'body').text.lower()
            if "too many requests" in page_text:
                print("❌ Rate limited by Nextdoor. (Server IP likely detected)")
                driver.save_screenshot(f"/opt/airflow/scraper/cookies/nd_ratelimit_{datetime.now().strftime('%H%M%S')}.png")
                # Save first 500 chars of page source for debugging
                print(f"📄 Page snippet: {page_text[:500]}")
                return "Failed: Rate limited"

            email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"], input#id_email')))
            email_field.send_keys(owner_email)
            
            password_field = driver.find_element(By.CSS_SELECTOR, 'input[name="password"], input#id_password')
            password_field.send_keys(owner_password)
            password_field.send_keys(Keys.ENTER)
            
            time.sleep(10)
            
            # 2FA Handling
            page_text = driver.find_element(By.TAG_NAME, 'body').text.lower()
            
            if "too many requests" in page_text:
                print("❌ Rate limited by Nextdoor.")
                driver.save_screenshot(f"/opt/airflow/scraper/cookies/nd_ratelimit_{datetime.now().strftime('%H%M%S')}.png")
                return "Failed: Rate limited"
            
            if any(x in page_text for x in ["brightdata", "kyc", "bad_endpoint", "住宅受限"]):
                print("❌ Proxy block detected (Bright Data KYC likely required).")
                driver.save_screenshot(f"/opt/airflow/scraper/cookies/proxy_block_{datetime.now().strftime('%H%M%S')}.png")
                return "Failed: Proxy block (Check Bright Data dashboard and complete KYC)"

            # Check for 2FA keywords or presence of a code input field
            is_2fa = any(k in page_text for k in ["login code", "enter code", "verification code", "verify your identity", "authenticator", "security code", "check your email", "confirm your account"])
            
            code_input = None
            code_selectors = ['input[name="code"]', 'input[id*="id_code"]', 'input[name*="verification"]']
            for selector in code_selectors:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    if el.is_displayed():
                        code_input = el
                        is_2fa = True
                        break
                except: pass

            if is_2fa:
                print("🔐 2FA screen detected!")
                two_fa_secret = Variable.get("nextdoor_2fa_secret", default_var=os.getenv("NEXTDOOR_2FA_SECRET"))
                
                if two_fa_secret:
                    print("🔐 Generating TOTP...")
                    import pyotp
                    code = pyotp.TOTP(two_fa_secret.replace(" ", "")).now()
                    if not code_input:
                        code_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="code"], input[id*="id_code"]')))
                    code_input.send_keys(code)
                    code_input.send_keys(Keys.ENTER)
                else:
                    print("🔐 Attempting to fetch OTP from Gmail via IMAP...")
                    from utils.email_manager import EmailManager
                    code = EmailManager.get_nextdoor_otp(owner_email, os.getenv("NEXTDOOR_APP_PASSWORD"))
                    
                    if code:
                        print(f"📥 OTP fetched: {code}")
                        if not code_input:
                            code_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="code"], input[id*="id_code"]')))
                        code_input.send_keys(code)
                        code_input.send_keys(Keys.ENTER)
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
                            page.locator('input[name="code"], input[id*="id_code"]').first.fill(code)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(5000)
                        else:
                            print("🔐 Email OTP fetch failed. Waiting for manual entry in 'nextdoor_owner_2fa' Airflow variable...")
                            Variable.set("nextdoor_owner_2fa", "WAITING")
                            # Simple poll logic
                            for _ in range(30): # Wait 5 minutes max
                                page.wait_for_timeout(10000)
                                manual_code = Variable.get("nextdoor_owner_2fa", default_var="")
                                if manual_code and manual_code != "WAITING":
                                    print(f"📥 Received manual code: {manual_code}")
                                    page.locator('input[name="code"], input[id*="id_code"]').first.fill(manual_code)
                                    page.keyboard.press("Enter")
                                    break
                
            page.wait_for_url(lambda url: "login" not in url.lower(), timeout=30000)
            cookies = browser_context.cookies()
            print(f"🍪 Retrieved {len(cookies)} cookies.")
            if cookies:
                cookie_names = [c['name'] for c in cookies]
                print(f"🍪 Cookie names: {cookie_names}")
                print(f"🍪 Full Cookies JSON: {json.dumps(cookies, indent=2)}")
            
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
