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
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def rotate_user_facebook_cookies(user_email, **context):
    """Log in to Facebook for a specific user and update their cookies."""
    # If triggered via another DAG for a specific user, only run for that user
    dag_run = context.get('dag_run')
    target_user = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    if target_user and target_user != user_email:
        print(f"⏭️ Skipping rotation for {user_email} as this run is targeted for {target_user}")
        return f"Skipped: Targeted run for {target_user}"

    from scrapers import FacebookScraper
    from user_credential_manager import UserCredentialManager
    
    manager = UserCredentialManager()
    creds = manager.get_facebook_credentials(user_email)
    
    if not creds or not creds.get("email") or not creds.get("password"):
        print(f"✗ Facebook credentials not found for user: {user_email}")
        return f"Failed: No credentials for {user_email}"

    email = creds["email"]
    password = creds["password"]
    
    printable_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
    print(f"🚀 Starting Facebook cookie rotation for User: {user_email} (FB Account: {printable_email})")
    
    scraper = FacebookScraper(headless=True)
    try:
        scraper._init_driver(headless=True)
        success = scraper.login(email, password)
        
        if success:
            cookies = scraper.driver.get_cookies()
            if cookies:
                # Save to user-specific cookie file and MongoDB
                manager.save_cookies(user_email, 'facebook', cookies)
                print(f"✅ Successfully rotated Facebook cookies for {user_email}.")
                return "Success"
            else:
                print(f"✗ Login succeeded for {user_email} but no cookies gathered.")
                raise ValueError("No cookies gathered after login.")
        else:
            print(f"✗ Facebook login failed for user {user_email}.")
            raise ValueError(f"Facebook login failed for {user_email}")
    finally:
        if scraper.driver:
            scraper.driver.quit()

# Create DAG
with DAG(
    'facebook_multi_user_cookie_rotation',
    default_args=default_args,
    description='Dynamic rotation of Facebook cookies for multiple users',
    schedule_interval='0 2 */2 * *', # Every 2 days at 2 AM
    catchup=False,
    tags=['maintenance', 'cookies', 'facebook', 'multi-user'],
    max_active_runs=1,
) as dag:

    # Get all users with facebook credentials
    try:
        manager = UserCredentialManager()
        users = manager.get_users_with_credentials('facebook')
    except Exception as e:
        print(f"Error fetching users: {e}")
        users = []

    if not users:
        # Create a dummy task if no users found to avoid DAG parsing errors
        def no_users(): print("No users with Facebook credentials found.")
        task = PythonOperator(task_id='no_users_found', python_callable=no_users)
    else:
        for user in users:
            user_email = user['email']
            user_id_clean = user_email.replace('@', '_at_').replace('.', '_')
            
            task = PythonOperator(
                task_id=f'rotate_fb_cookies_{user_id_clean}',
                python_callable=rotate_user_facebook_cookies,
                op_kwargs={'user_email': user_email},
                pool='scraper_pool',
            )
