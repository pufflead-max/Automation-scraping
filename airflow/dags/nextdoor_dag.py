"""
Airflow DAG for Nextdoor lead scraping with dynamic URL loading.
Reads URLs from text file and creates separate tasks for each neighborhood/feed.

NOTE: Requires Nextdoor authentication cookies to be configured.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json

# Add scraper src to path
sys.path.insert(0, '/opt/airflow/scraper/src')

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=1),
}


def load_nextdoor_urls():
    """Load Nextdoor URLs from file or Airflow variable."""
    from utils.url_loader import get_scraper_urls
    
    # Try to get from Airflow variable first
    try:
        urls_raw = Variable.get("nextdoor_target_url", default_var="")
        if urls_raw:
            urls = [url.strip() for url in urls_raw.replace('\n', ',').split(',') if url.strip()]
            if urls:
                return urls
    except:
        pass
    
    # Load from file
    urls = get_scraper_urls(
        "nextdoor",
        default_url="https://nextdoor.com/news_feed/"
    )
    
    return urls


def load_nextdoor_cookies():
    """
    Load Nextdoor cookies from environment or file.
    
    Returns:
        dict: Cookies dictionary
    """
    # Try to load from environment variable
    cookies_json = os.getenv('NEXTDOOR_COOKIES')
    if cookies_json:
        try:
            return json.loads(cookies_json)
        except:
            pass
    
    # Try to load from Airflow variable as fallback for env
    try:
        cookies_str = Variable.get("nextdoor_cookies", default_var="")
        if cookies_str:
            return json.loads(cookies_str)
    except:
        pass
    
    # Try to load from file
    cookies_file = os.getenv('NEXTDOOR_COOKIES_FILE', '/opt/airflow/scraper/cookies/nextdoor_cookies.json')
    if os.path.exists(cookies_file):
        try:
            with open(cookies_file, 'r') as f:
                return json.load(f)
        except:
            pass
    
    raise ValueError(
        "Nextdoor cookies not configured. "
        "Set NEXTDOOR_COOKIES env var, nextdoor_cookies Airflow Var, or create /opt/airflow/scraper/cookies/nextdoor_cookies.json"
    )


def scrape_nextdoor_url(target_url: str, url_index: int, max_pages: int = 5):
    """
    Python callable to scrape a specific Nextdoor URL.
    
    Args:
        target_url: The Nextdoor URL to scrape
        url_index: Index of the URL (for logging)
        max_pages: Maximum number of pages to scrape
    """
    from main import run_nextdoor_scraper
    
    print(f"Starting Nextdoor scrape for URL #{url_index + 1}: {target_url}")
    print(f"Max pages: {max_pages}")
    
    try:
        # Load cookies
        cookies = load_nextdoor_cookies()
        print(f"✓ Loaded cookies")
        
        # Run scraper
        leads = run_nextdoor_scraper(
            target=target_url,
            cookies=cookies,
            save_to_db=True,
            max_pages=max_pages
        )
        
        print(f"✓ Successfully scraped {len(leads)} leads from {target_url}")
        return len(leads)
        
    except Exception as e:
        print(f"✗ Failed to scrape Nextdoor {target_url}: {e}")
        raise


# Define the DAG
with DAG(
    'nextdoor_scraper',
    default_args=default_args,
    description='Scrape service leads from Nextdoor (multi-URL support)',
    schedule_interval='0 3 * * *',  # Run daily at 3 AM
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['scraping', 'nextdoor', 'leads'],
    max_active_runs=1,
    concurrency=1, # Nextdoor is sensitive to multiple sessions, run sequentially by default or very limited
) as dag:

    # Load URLs and create dynamic tasks
    nextdoor_urls = load_nextdoor_urls()
    
    scrape_tasks = []
    for idx, url in enumerate(nextdoor_urls):
        task_id = f'scrape_nextdoor_url_{idx + 1}'
        
        task = PythonOperator(
            task_id=task_id,
            python_callable=scrape_nextdoor_url,
            op_kwargs={
                'target_url': url,
                'url_index': idx,
                'max_pages': 5,
            },
        )
        scrape_tasks.append(task)

    # Push to GHL task
    def push_nextdoor_leads_to_ghl():
        """Push Nextdoor leads from MongoDB to GHL."""
        from push_leads import push_leads
        print("Starting Nextdoor push to GHL")
        push_leads(source="nextdoor")

    push_task = PythonOperator(
        task_id='push_nextdoor_to_ghl',
        python_callable=push_nextdoor_leads_to_ghl,
    )

    # Optional: Add summary task
    def summarize_nextdoor_results(**context):
        """
        Summarize the results from Nextdoor scraping.
        """
        from database import get_db_manager
        from datetime import datetime, timedelta
        
        db = get_db_manager()
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        jobs = db.find_many(
            "scrape_jobs",
            {"scraper": "nextdoor", "started_at": {"$gte": yesterday}}
        )
        
        total_items = sum(job.get('items_saved', 0) for job in jobs)
        successful_jobs = sum(1 for job in jobs if job.get('status') == 'completed')
        failed_jobs = sum(1 for job in jobs if job.get('status') == 'failed')
        
        print("\n" + "="*60)
        print("NEXTDOOR SCRAPING SUMMARY")
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
        python_callable=summarize_nextdoor_results,
        provide_context=True,
    )

    # Set task dependencies
    scrape_tasks >> push_task >> summary_task
