"""
Airflow DAG for Nextdoor lead scraping.
Runs daily to extract service leads from Nextdoor feed.

NOTE: Requires Nextdoor authentication cookies to be configured.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import sys
import json
import os

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

dag = DAG(
    'nextdoor_scraper',
    default_args=default_args,
    description='Scrape service leads from Nextdoor',
    schedule_interval='0 3 * * *',  # Run daily at 3 AM
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['scraping', 'nextdoor', 'leads'],
    max_active_runs=1,
)


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
    
    # Try to load from file
    cookies_file = os.getenv('NEXTDOOR_COOKIES_FILE', '/opt/airflow/config/nextdoor_cookies.json')
    if os.path.exists(cookies_file):
        try:
            with open(cookies_file, 'r') as f:
                return json.load(f)
        except:
            pass
    
    raise ValueError(
        "Nextdoor cookies not configured. "
        "Set NEXTDOOR_COOKIES env var or create /opt/airflow/config/nextdoor_cookies.json"
    )


def scrape_nextdoor_feed(max_pages: int = 5):
    """
    Python callable to scrape Nextdoor feed.
    
    Args:
        max_pages: Maximum number of pages to scrape
    """
    from main import run_nextdoor_scraper
    
    print("Starting Nextdoor feed scrape")
    print(f"Max pages: {max_pages}")
    
    try:
        # Load cookies
        cookies = load_nextdoor_cookies()
        print(f"✓ Loaded {len(cookies)} cookies")
        
        # Run scraper
        leads = run_nextdoor_scraper(
            cookies=cookies,
            save_to_db=True,
            max_pages=max_pages
        )
        
        print(f"✓ Successfully scraped {len(leads)} leads from Nextdoor")
        return len(leads)
        
    except Exception as e:
        print(f"✗ Failed to scrape Nextdoor: {e}")
        raise


# Create scraping task
scrape_task = PythonOperator(
    task_id='scrape_nextdoor_feed',
    python_callable=scrape_nextdoor_feed,
    op_kwargs={
        'max_pages': 30,  # Increased from 5 to 30 to get more records
    },
    dag=dag,
)


# Optional: Add summary task
def summarize_nextdoor_results(**context):
    """
    Summarize the results from Nextdoor scraping.
    """
    from database import get_db_manager
    from datetime import datetime, timedelta
    
    db = get_db_manager()
    
    # Get Nextdoor jobs from the last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    jobs = db.find_many(
        "scrape_jobs",
        {
            "scraper": "nextdoor",
            "started_at": {"$gte": yesterday}
        }
    )
    
    # Get Nextdoor leads from last 24 hours
    leads = db.find_many(
        "leads",
        {
            "source": "nextdoor",
            "scraped_date": {"$gte": yesterday}
        }
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
    print(f"Leads in database: {len(leads)}")
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
    dag=dag,
)

# Set task dependencies
scrape_task >> summary_task
