from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os

# Add scraper modules to path
sys.path.insert(0, "/opt/airflow/scraper/src")

from user_credential_manager import UserCredentialManager

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def rotate_facebook_owner_cookies(**context):
    """Log in to Facebook for the central owner account and update cookies."""
    from scrapers import FacebookScraper
    from user_credential_manager import UserCredentialManager

    owner_email = Variable.get("facebook_owner_email", default_var=os.getenv("FACEBOOK_EMAIL"))
    owner_password = Variable.get("facebook_owner_password", default_var=os.getenv("FACEBOOK_PASSWORD"))

    if not owner_email or not owner_password:
        print(" Central Facebook owner credentials not found in Airflow Variables or Env.")
        return "Failed: No owner credentials"

    manager = UserCredentialManager()

    printable_email = owner_email[:3] + "***" + owner_email[owner_email.find("@"):] if "@" in owner_email else owner_email[:4] + "***"
    print(f" Starting Facebook cookie rotation for OWNER account: {printable_email}")

    scraper = FacebookScraper(headless=True, use_proxy=True)
    try:
        scraper._init_driver(headless=True)
        success = scraper.login(owner_email, owner_password)

        if success:
            cookies = scraper.driver.get_cookies()
            if cookies:
                # Save owner cookies
                manager.save_cookies(owner_email, 'facebook', cookies)
                print(f" Successfully rotated Facebook cookies for owner {printable_email}.")
                # Also set a global variable for scrapers to find easily
                Variable.set("facebook_last_rotation", datetime.utcnow().isoformat())
                return "Success"
            else:
                raise ValueError("No cookies gathered after login.")
        else:
            raise ValueError(f"Facebook login failed for owner {owner_email}")
    finally:
        scraper.quit()

with DAG(
    'facebook_owner_cookie_rotation',
    default_args=default_args,
    description='Rotation of Facebook cookies for the central owner account',
    schedule_interval=None, # Only triggered by on_failure_callback
    catchup=False,
    tags=['maintenance', 'cookies', 'facebook', 'owner'],
    max_active_runs=1,
) as dag:

    rotate_task = PythonOperator(
        task_id='rotate_facebook_owner_cookies',
        python_callable=rotate_facebook_owner_cookies,
        pool='scraper_pool',
    )
