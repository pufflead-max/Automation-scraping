from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json
from airflow_utils.callbacks import trigger_cookie_rotation

# Add scraper modules to path
sys.path.insert(0, "/opt/airflow/scraper/src")

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
    'on_failure_callback': trigger_cookie_rotation,
}

def run_facebook_unlimited_scraper(**context):
    """Execute the Facebook scraper without limit (scrapes maximum posts)."""
    from scrapers import FacebookScraper
    from utils.url_loader import get_scraper_urls
    
    # Get configuration from centralized loader (checks Var, DB, then File)
    # We check the Var here first to maintain compatibility with existing setup
    try:
        urls_raw = Variable.get("facebook_target_url", default_var="")
        if urls_raw:
            target_urls = [url.strip() for url in urls_raw.replace('\n', ',').split(',') if url.strip()]
        else:
            target_urls = get_scraper_urls("facebook", default_url="https://www.facebook.com/share/g/14Tv25M9ns8/?mibextid=wwXIfr")
    except:
        target_urls = get_scraper_urls("facebook", default_url="https://www.facebook.com/share/g/14Tv25M9ns8/?mibextid=wwXIfr")
    
    # Setting limit to 0 means "unlimited" in our updated scraper
    limit = 0
    headless = Variable.get("facebook_headless", default_var="true").lower() == "true"
    
    # Try to get cookies from variable, otherwise scraper will look for file
    cookies = None
    try:
        cookies_str = Variable.get("facebook_cookies", default_var="")
        if cookies_str:
            cookies = json.loads(cookies_str)
    except:
        print("Could not load cookies from Airflow Variable, using file if available")

    total_results = 0
    scraper = FacebookScraper(cookies=cookies, headless=headless)
    
    for target_url in target_urls:
        print(f"Starting UNLIMITED Facebook scrape for {target_url}")
        try:
            results = scraper.run(target=target_url, limit=limit, save_to_db=True)
            print(f"Successfully scraped {len(results)} posts from {target_url} (MAXIMUM)")
            total_results += len(results)
        except Exception as e:
            print(f"Error scraping {target_url}: {str(e)}")
            continue
    
    print(f"Total successfully scraped posts across all URLs: {total_results} (MAXIMUM)")
    return total_results

with DAG(
    'facebook_unlimited_scraper_dag',
    default_args=default_args,
    description='Scrape Facebook pages without limit (maximum posts)',
    schedule_interval=None, # Only run manually
    catchup=False,
    tags=['scraping', 'facebook', 'unlimited'],
) as dag:

    scrape_task = PythonOperator(
        task_id='scrape_facebook_unlimited',
        python_callable=run_facebook_unlimited_scraper,
    )

    def push_facebook_leads_to_ghl():
        """Push Facebook leads from MongoDB to GHL."""
        from push_leads import push_leads
        print("Starting Facebook push to GHL")
        push_leads(source="facebook")

    push_task = PythonOperator(
        task_id='push_facebook_to_ghl',
        python_callable=push_facebook_leads_to_ghl,
    )

    scrape_task >> push_task
