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

def rotate_facebook_cookies(**context):
    """Log in to Facebook and update cookies in Airflow Variable."""
    from scrapers import FacebookScraper
    
    # These are now initialized from .env -> variables.json -> Airflow Variable at startup
    email = Variable.get("facebook_email", default_var="ENTER_YOUR_EMAIL")
    password = Variable.get("facebook_password", default_var="ENTER_YOUR_PASSWORD")
    
    if email == "ENTER_YOUR_EMAIL" or password == "ENTER_YOUR_PASSWORD":
        print("✗ Facebook credentials are not set in Airflow Variables.")
        print("👉 Please update them in the Airflow UI or your .env file and restart.")
        raise ValueError("Facebook credentials missing or unconfigured.")

    printable_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
    print(f"Starting Facebook cookie rotation for {printable_email}")
    
    scraper = FacebookScraper(headless=True)
    try:
        scraper._init_driver(headless=True)
        success = scraper.login(email, password)
        
        if success:
            cookies = scraper._save_cookies()
            if cookies:
                # Update Airflow Variable
                Variable.set("facebook_cookies", json.dumps(cookies))
                print("✓ Successfully rotated Facebook cookies.")
                return "Success"
            else:
                print("✗ Login succeeded but no cookies were gathered.")
                raise ValueError("No cookies gathered after login.")
        else:
            print("✗ Facebook login failed.")
            raise ValueError("Facebook login failed.")
    finally:
        if scraper.driver:
            scraper.driver.quit()

with DAG(
    'facebook_cookie_rotation_dag',
    default_args=default_args,
    description='Rotation of Facebook scraper cookies',
    schedule_interval='0 0 */2 * *', # Every 2 days at midnight
    catchup=False,
    tags=['maintenance', 'cookies', 'facebook'],
) as dag:

    fb_rotation = PythonOperator(
        task_id='rotate_facebook_cookies',
        python_callable=rotate_facebook_cookies,
    )
