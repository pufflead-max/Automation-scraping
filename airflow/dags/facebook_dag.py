"""
Airflow DAG for Facebook lead scraping with dynamic URL loading.
Reads URLs from text file and creates separate tasks for each URL.
"""

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
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}


def load_facebook_urls():
    """Load Facebook URLs from file or Airflow variable."""
    from utils.url_loader import get_scraper_urls
    
    # Try to get from Airflow variable first
    try:
        urls_raw = Variable.get("facebook_target_url", default_var="")
        if urls_raw:
            urls = [url.strip() for url in urls_raw.replace('\n', ',').split(',') if url.strip()]
            if urls:
                print(f"✓ Successfully loaded {len(urls)} URLs from Airflow Variable 'facebook_target_url'")
                return urls
    except Exception as e:
        print(f"Error loading facebook_target_url variable: {e}")
    
    raise ValueError("No Facebook URLs specified. Please set 'facebook_target_url' Airflow Variable.")


def scrape_facebook_url(target_url: str, url_index: int, **context):
    """
    Execute the Facebook scraper for a single URL.
    
    Args:
        target_url: The Facebook URL to scrape
        url_index: Index of the URL (for logging)
    """
    from scrapers import FacebookScraper
    
    limit = int(Variable.get("facebook_post_limit", default_var="25"))
    headless = Variable.get("facebook_headless", default_var="true").lower() == "true"
    
    # Try to get cookies from variable, otherwise scraper will look for file
    cookies = None
    try:
        cookies_str = Variable.get("facebook_cookies", default_var="")
        if cookies_str:
            cookies = json.loads(cookies_str)
    except:
        print("Could not load cookies from Airflow Variable")

    print(f"Starting Facebook scrape for URL #{url_index + 1}: {target_url}")
    
    try:
        scraper = FacebookScraper(cookies=cookies, headless=headless)
        results = scraper.run(target=target_url, limit=limit, save_to_db=True)
        print(f"✓ Successfully scraped {len(results)} posts from {target_url}")
        return len(results)
    except Exception as e:
        print(f"✗ Error scraping {target_url}: {str(e)}")
        raise


# Create DAG
with DAG(
    'facebook_scraper_dag',
    default_args=default_args,
    description='Scrape Facebook pages (multi-URL support)',
    schedule_interval='@daily',
    catchup=False,
    tags=['scraping', 'facebook'],
    max_active_runs=1,  # Only 1 DAG run at a time
    concurrency=2,  # Limit to 2 concurrent tasks within the DAG
) as dag:

    # Load URLs and create dynamic tasks
    facebook_urls = load_facebook_urls()
    
    scrape_tasks = []
    for idx, url in enumerate(facebook_urls):
        # Create a safe task ID from the URL
        task_id = f'scrape_facebook_url_{idx + 1}'
        
        task = PythonOperator(
            task_id=task_id,
            python_callable=scrape_facebook_url,
            op_kwargs={
                'target_url': url,
                'url_index': idx,
            },
        )
        scrape_tasks.append(task)
    
    # Push to GHL task
    def push_facebook_leads_to_ghl():
        """Push Facebook leads from MongoDB to GHL."""
        from push_leads import push_leads
        print("Starting Facebook push to GHL")
        push_leads(source="facebook")

    push_task = PythonOperator(
        task_id='push_facebook_to_ghl',
        python_callable=push_facebook_leads_to_ghl,
    )
    
    # Summary task
    def summarize_facebook_results(**context):
        """
        Summarize the results from Facebook scraping.
        """
        from database import get_db_manager
        from datetime import datetime, timedelta
        
        db = get_db_manager()
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        jobs = db.find_many(
            "scrape_jobs",
            {"scraper": "facebook", "started_at": {"$gte": yesterday}}
        )
        
        total_items = sum(job.get('items_saved', 0) for job in jobs)
        successful_jobs = sum(1 for job in jobs if job.get('status') == 'completed')
        failed_jobs = sum(1 for job in jobs if job.get('status') == 'failed')
        
        print("\n" + "="*60)
        print("FACEBOOK SCRAPING SUMMARY")
        print("="*60)
        print(f"Total jobs: {len(jobs)}")
        print(f"Successful: {successful_jobs}")
        print(f"Failed: {failed_jobs}")
        print(f"Total leads scraped: {total_items}")
        print("="*60 + "\n")
        
        return {
            'total_jobs': len(jobs),
            'successful': successful_jobs,
            'failed': failed_jobs,
            'total_leads': total_items
        }

    summary_task = PythonOperator(
        task_id='summarize_results',
        python_callable=summarize_facebook_results,
        provide_context=True,
    )

    # Set dependencies: all scrape tasks run in parallel, then push, then summary
    scrape_tasks >> push_task >> summary_task
