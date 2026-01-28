"""
Airflow DAG for Craigslist lead scraping.
Runs daily to extract service leads from Craigslist across multiple categories.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import os
import sys

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

# Define the DAG
dag = DAG(
    'craigslist_scraper',
    default_args=default_args,
    description='Scrape service leads from Craigslist',
    schedule_interval='0 2 * * *',  # Run daily at 2 AM
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['scraping', 'craigslist', 'leads'],
    max_active_runs=1,
)


def scrape_craigslist_category(category_url: str, category_name: str):
    """
    Python callable to scrape a specific Craigslist category.
    
    Args:
        category_url: URL of the category to scrape
        category_name: Name of the category for logging
    """
    from main import run_craigslist_scraper
    
    print(f"Starting scrape for category: {category_name}")
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


# Define target categories to scrape
# Format: (category_name, category_url)
CATEGORIES = [
    ('automotive', 'https://boston.craigslist.org/search/aos'),
    ('beauty', 'https://boston.craigslist.org/search/bts'),
    ('computer', 'https://boston.craigslist.org/search/cps'),
    ('household', 'https://boston.craigslist.org/search/hss'),
    ('skilled_trade', 'https://boston.craigslist.org/search/sks'),
    ('real_estate', 'https://boston.craigslist.org/search/rts'),
    ('labor_move', 'https://boston.craigslist.org/search/lbs'),
    ('legal', 'https://boston.craigslist.org/search/lgs'),
    ('financial', 'https://boston.craigslist.org/search/fns'),
    ('health_wellness', 'https://boston.craigslist.org/search/hws'),
]


# Create a task for each category
scraping_tasks = []

for category_name, category_url in CATEGORIES:
    task = PythonOperator(
        task_id=f'scrape_{category_name}',
        python_callable=scrape_craigslist_category,
        op_kwargs={
            'category_url': category_url,
            'category_name': category_name,
        },
        dag=dag,
    )
    scraping_tasks.append(task)


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
# All scraping tasks run in parallel, then summary runs after all complete
scraping_tasks >> summary_task
