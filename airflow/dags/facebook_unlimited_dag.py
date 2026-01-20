from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json

# Add scraper module to path
sys.path.append("/opt/airflow/scraper/src")

from scrapers import FacebookScraper
from config import get_scraper_config

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

def run_facebook_unlimited_scraper(**context):
    """Execute the Facebook scraper without limit (scrapes maximum posts)."""
    # Get configuration from Airflow variables or defaults
    target_urls_raw = Variable.get("facebook_target_url", default_var="https://www.facebook.com/nike")
    # Support multiple URLs separated by commas or newlines
    target_urls = [url.strip() for url in target_urls_raw.replace('\n', ',').split(',') if url.strip()]
    
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

    scrape_task
