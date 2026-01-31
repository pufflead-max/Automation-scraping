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
    email = Variable.get("nextdoor_email", default_var="ENTER_YOUR_EMAIL")
    password = Variable.get("nextdoor_password", default_var="ENTER_YOUR_PASSWORD")
    
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
            
            # Wait for email field specifically - this confirms we are on the right page
            print("Checking for login form...")
            page.wait_for_selector('input[name="email"], input#id_email', timeout=20000)
            page.type('input[name="email"], input#id_email', email, delay=100)
            
            # Fill password with human-like delay
            page.type('input[name="password"], input#id_password', password, delay=100)
            
            # Click login
            login_button = page.locator('button[type="submit"], button:has-text("Log in")').first
            login_button.click()
            
            # Wait for navigation or a change in URL
            try:
                page.wait_for_url(lambda url: "login" not in url.lower() and "signup" not in url.lower(), timeout=15000)
            except Exception:
                print("Navigation timeout - checking page state...")
            
            # Check for common error messages
            error_feedback = page.locator('.error-message, [role="alert"], .alert-danger').first
            if error_feedback.is_visible():
                error_text = error_feedback.inner_text()
                print(f"Nextdoor login error on page: {error_text}")
            
            # Check if logged in (url shouldn't contain login/signup)
            current_url = page.url.lower()
            if "login" not in current_url and "signup" not in current_url:
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
                print(f"✗ Nextdoor login failed. Current URL: {current_url}")
                raise ValueError("Nextdoor login failed.")
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
