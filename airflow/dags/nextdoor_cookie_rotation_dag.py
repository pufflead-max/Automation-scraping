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
                        print("🔐 Waiting for manual OTP in 'nextdoor_owner_2fa' variable...")
                        Variable.set("nextdoor_owner_2fa", "WAITING")
                        for _ in range(30):
                            time.sleep(10)
                            manual_code = Variable.get("nextdoor_owner_2fa", default_var="")
                            if manual_code and manual_code != "WAITING":
                                if not code_input:
                                    code_input = driver.find_element(By.CSS_SELECTOR, 'input[name="code"], input[id*="id_code"]')
                                code_input.send_keys(manual_code)
                                code_input.send_keys(Keys.ENTER)
                                break
            
            time.sleep(10)

        # Final Verification
        try:
            # Specifically check for cookies that indicate a session
            wait.until(lambda d: any(x in d.current_url.lower() for x in ["news_feed", "home", "neighborhood"]))
            
            cookies = driver.get_cookies()
            nd_session_cookies = [c for c in cookies if 'nd' in c['name'] or 'session' in c['name'].lower()]
            
            if not nd_session_cookies:
                print("⚠️ URL looks correct but NO session cookies found. We might be on an error page.")
                print(f"📄 Page Title: {driver.title}")
                print(f"📄 Page Text Preview: {driver.find_element(By.TAG_NAME, 'body').text[:300]}")
                driver.save_screenshot(f"/opt/airflow/scraper/cookies/nd_no_cookies_{datetime.now().strftime('%H%M%S')}.png")
                # If we have 0 cookies, it's not a success.
                if len(cookies) == 0:
                    return "Failed: 0 cookies retrieved"

            print(f"✅ Navigation Verified! URL: {driver.current_url}")
        except:
            print(f"⚠️ Navigation verification timeout. URL: {driver.current_url}")

        cookies = driver.get_cookies()
        print(f"🍪 Retrieved {len(cookies)} total cookies.")
        essential_cookies = [c['name'] for c in cookies if 'nd' in c['name'] or 'session' in c['name'].lower()]
        print(f"🍪 Essential cookies found: {essential_cookies}")
        
        if len(cookies) > 0:
            manager.save_cookies(owner_email, 'nextdoor', cookies)
            print(f"✅ Cookies saved for {owner_email}.")
        else:
            print(f"⚠️ No cookies captured for {owner_email}, skipping save.")
            return "Failed: No cookies captured"

        Variable.set("nextdoor_last_rotation", datetime.utcnow().isoformat())
        return "Success"
        
    except Exception as e:
        print(f"❌ Error during rotation: {e}")
        driver.save_screenshot("/opt/airflow/scraper/cookies/selenium_error.png")
        return f"Failed: {str(e)}"
    finally:
        driver.quit()
        if display:
            print("🖥️ Stopping Virtual Display...")
            display.stop()

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
