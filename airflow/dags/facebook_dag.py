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
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def run_facebook_scraper(**context):
    """Execute the Facebook scraper."""
    # Get configuration from Airflow variables or defaults
    target_urls_raw = Variable.get("facebook_target_url", default_var="https://www.facebook.com/share/g/1ahUgW7G9w/?mibextid=wwXIfr")
    # Support multiple URLs separated by commas or newlines
    target_urls = [url.strip() for url in target_urls_raw.replace('\n', ',').split(',') if url.strip()]
    
    limit = int(Variable.get("facebook_post_limit", default_var="100"))
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
        print(f"Starting Facebook scrape for {target_url}")
        try:
            results = scraper.run(target=target_url, limit=limit, save_to_db=True)
            print(f"Successfully scraped {len(results)} posts from {target_url}")
            total_results += len(results)
        except Exception as e:
            print(f"Error scraping {target_url}: {str(e)}")
            continue
    
    print(f"Total successfully scraped posts across all URLs: {total_results}")
    return total_results

with DAG(
    'facebook_scraper_dag',
    default_args=default_args,
    description='Scrape Facebook pages',
    schedule_interval='@daily',
    catchup=False,
    tags=['scraping', 'facebook'],
) as dag:

    scrape_task = PythonOperator(
        task_id='scrape_facebook',
        python_callable=run_facebook_scraper,
    )

    scrape_task
