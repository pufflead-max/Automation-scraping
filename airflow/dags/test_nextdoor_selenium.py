import os
import time
import random
import zipfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
from pyvirtualdisplay import Display
from dotenv import load_dotenv

load_dotenv()

def create_proxy_auth_extension(proxy_host, proxy_port, proxy_user, proxy_pass, scheme='http', plugin_path='proxy_auth_plugin.zip'):
    """Create a Chrome extension to handle proxy authentication."""
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "%s",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
            callbackFn,
            {urls: ["<all_urls>"]},
            ['blocking']
    );
    """ % (scheme, proxy_host, proxy_port, proxy_user, proxy_pass)

    with zipfile.ZipFile(plugin_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return plugin_path

def test_nextdoor_selenium():
    email = os.getenv("NEXTDOOR_EMAIL")
    password = os.getenv("NEXTDOOR_PASSWORD")
    proxy_server = os.getenv("BRIGHTDATA_PROXY_SERVER") # brd.superproxy.io:33335
    proxy_user = os.getenv("BRIGHTDATA_PROXY_USER")
    proxy_pass = os.getenv("BRIGHTDATA_PROXY_PASS")

    # Start Xvfb
    print(" Starting Virtual Display (Xvfb)...")
    display = Display(visible=0, size=(1280, 800))
    display.start()

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,800")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    if proxy_server:
        print(f" Configuring Proxy: {proxy_server}")
        host, port = proxy_server.split(':')
        # Use http scheme for the proxy tunnel itself
        plugin_path = create_proxy_auth_extension(host, port, proxy_user, proxy_pass)
        chrome_options.add_extension(plugin_path)

    # Add stealth arguments
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        # Use existing chromedriver in container
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # CLEAR COOKIES TO START FRESH
        driver.delete_all_cookies()

        stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="MacIntel",  # Must match the macOS User-Agent above
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

        # 1. Check IP
        print(" Verifying Connection...")
        driver.get("https://api64.ipify.org?format=json")
        print(f" Current IP: {driver.find_element(By.TAG_NAME, 'body').text}")

        # 2. Go to Nextdoor
        print(" Navigating to Nextdoor...")
        driver.get("https://nextdoor.com/news_feed/")
        time.sleep(5)

        print(f" Current URL: {driver.current_url}")

        # --- Suspended account check ---
        if "suspended" in driver.current_url.lower() or "suspended" in driver.page_source.lower():
            print(" Account is SUSPENDED. Cannot obtain ndbr_at cookie. Use a fresh account.")
            driver.save_screenshot("nd_suspended.png")
            return

        if "login" in driver.current_url.lower():
            print(" Login required. Entering credentials...")

            # Human-like: focus email field, type with small random delays
            email_field = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "email")))
            email_field.click()
            for char in email:
                email_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            time.sleep(random.uniform(0.8, 1.5))  # Pause between fields

            password_field = driver.find_element(By.NAME, "password")
            password_field.click()
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            time.sleep(random.uniform(0.5, 1.2))  # Brief pause before submit
            password_field.send_keys(Keys.ENTER)

            print(" Waiting for login/2FA screen...")
            time.sleep(10)

            # --- Post-login suspension check ---
            if "suspended" in driver.current_url.lower() or "suspended" in driver.page_source.lower():
                print(" Account suspended after login attempt. Cannot obtain ndbr_at cookie.")
                driver.save_screenshot("nd_suspended_post_login.png")
                return

            # 2FA HANDLING
            page_source = driver.page_source.lower()
            if any(x in page_source for x in ["login code", "enter code", "verification code", "verify your identity"]):
                print(" 2FA screen detected! Attempting to fetch code...")

                # Try TOTP first
                two_fa_secret = os.getenv("NEXTDOOR_2FA_SECRET")
                code = None

                if two_fa_secret:
                    import pyotp
                    code = pyotp.TOTP(two_fa_secret.replace(" ", "")).now()
                    print(f" Generated TOTP: {code}")
                else:
                    # Try Gmail
                    print(" Checking Gmail for OTP...")
                    from utils.email_manager import EmailManager
                    app_pass = os.getenv("NEXTDOOR_APP_PASSWORD")
                    code = EmailManager.get_nextdoor_otp(email, app_pass) if app_pass else None

                if code:
                    print(f" Entering code: {code}")
                    code_input = driver.find_element(By.NAME, "code")
                    code_input.send_keys(code)
                    code_input.send_keys(Keys.ENTER)
                    print(" Submitted 2FA. Waiting for redirect...")
                    time.sleep(10)
                else:
                    print(" Could not get 2FA code automatically.")
                    driver.save_screenshot("nd_2fa_manual_needed.png")

        # 3. Final Verification
        cookies = driver.get_cookies()
        has_session = any(c['name'] == 'ndbr_at' for c in cookies)

        print(f" Retrieved {len(cookies)} cookies.")
        if has_session:
            print(" Login SUCCESS! ndbr_at cookie found.")
        else:
            print(" Login FAILED: No ndbr_at cookie.")
            # Save dump for debug
            with open("nd_selenium_debug_source.html", "w") as f:
                f.write(driver.page_source)

    except Exception as e:
        print(f" Error during test: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
        display.stop()
        if os.path.exists('proxy_auth_plugin.zip'):
            os.remove('proxy_auth_plugin.zip')

if __name__ == "__main__":
    test_nextdoor_selenium()
