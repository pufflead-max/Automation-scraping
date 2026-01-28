"""
Airflow DAG for Craigslist lead scraping with dynamic URL loading.
Reads URLs from text file and creates separate tasks for each category.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import os
import sys
import re

# Add scraper src to path
sys.path.insert(0, '/opt/airflow/scraper/src')

# Default arguments for the DAG
default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}


def load_craigslist_urls():
    """Load Craigslist URLs from file."""
    from utils.url_loader import get_scraper_urls
    
    urls = get_scraper_urls("craigslist")
    
    # If no URLs from file, use defaults
    if not urls:
        urls = [
            'https://boston.craigslist.org/search/aos',
            'https://boston.craigslist.org/search/bts',
            'https://boston.craigslist.org/search/cps',
            'https://boston.craigslist.org/search/hss',
            'https://boston.craigslist.org/search/sks',
            'https://boston.craigslist.org/search/rts',
            'https://boston.craigslist.org/search/lbs',
            'https://boston.craigslist.org/search/lgs',
            'https://boston.craigslist.org/search/fns',
            'https://boston.craigslist.org/search/hws',
        ]
    
    return urls


def extract_category_from_url(url: str) -> str:
    """Extract category name from Craigslist URL."""
    # Try to extract category code from URL
    match = re.search(r'/search/([a-z]+)', url)
    if match:
        return match.group(1)
    
    # Fallback: use last part of URL
    return url.rstrip('/').split('/')[-1]


def scrape_craigslist_url(category_url: str, category_name: str, url_index: int):
    """
    Python callable to scrape a specific Craigslist URL.
    
    Args:
        category_url: URL to scrape
        category_name: Name of the category for logging
        url_index: Index of the URL
    """
    from main import run_craigslist_scraper
    
    print(f"Starting scrape for URL #{url_index + 1}: {category_name}")
    print(f"Target URL: {category_url}")
    
    try:
        leads = run_craigslist_scraper(
            target=category_url,
            category=category_name,
            save_to_db=True,
            headless=True
        )
        
        print(f"✓ Successfully scraped {len(leads)} leads from {category_name}")
        return len(leads)
        
    except Exception as e:
        print(f"✗ Failed to scrape {category_name}: {e}")
        raise


# Define the DAG
dag = DAG(
    'craigslist_scraper',
    default_args=default_args,
    description='Scrape service leads from Craigslist (multi-URL support)',
    schedule_interval='0 2 * * *',  # Run daily at 2 AM
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['scraping', 'craigslist', 'leads'],
    max_active_runs=1,
)

# Load URLs and create dynamic tasks
craigslist_urls = load_craigslist_urls()

scraping_tasks = []

for idx, url in enumerate(craigslist_urls):
    category_name = extract_category_from_url(url)
    task_id = f'scrape_{category_name}_{idx + 1}' if idx > 0 and any(extract_category_from_url(u) == category_name for u in craigslist_urls[:idx]) else f'scrape_{category_name}'
    
    task = PythonOperator(
        task_id=task_id,
        python_callable=scrape_craigslist_url,
        op_kwargs={
            'category_url': url,
            'category_name': category_name,
            'url_index': idx,
        },
        dag=dag,
    )
    scraping_tasks.append(task)


def push_craigslist_leads_to_ghl():
    """Push Craigslist leads from MongoDB to GHL."""
    from push_leads import push_leads
    print("Starting Craigslist push to GHL")
    push_leads(source="craigslist")

push_task = PythonOperator(
    task_id='push_craigslist_to_ghl',
    python_callable=push_craigslist_leads_to_ghl,
    dag=dag,
)


# Optional: Add a summary task at the end
def summarize_scraping_results(**context):
    """
    Summarize the results from all scraping tasks.
    """
    from database import get_db_manager
    from datetime import datetime, timedelta
    
    db = get_db_manager()
    
    # Get jobs from the last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    jobs = db.find_many(
        "scrape_jobs",
        {
            "scraper": "craigslist",
            "started_at": {"$gte": yesterday}
        }
    )
    
    total_items = sum(job.get('items_saved', 0) for job in jobs)
    successful_jobs = sum(1 for job in jobs if job.get('status') == 'completed')
    failed_jobs = sum(1 for job in jobs if job.get('status') == 'failed')
    
    print("\n" + "="*60)
    print("CRAIGSLIST SCRAPING SUMMARY")
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
    python_callable=summarize_scraping_results,
    provide_context=True,
    dag=dag,
)


# Set task dependencies
# All scraping tasks run in parallel, then push to GHL, then summary runs
scraping_tasks >> push_task >> summary_task
