# airflow DAG
"""
Airflow DAG for Craigslist lead scraping with dynamic URL loading.
Reads URLs from text file and creates separate tasks for each category.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import os
import sys
import re
import json

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

def get_user_details(email: str):
    """Fetch user details from MongoDB by email."""
    from pymongo import MongoClient
    mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017")
    client = MongoClient(mongo_uri)
    db = client["PUFF"]
    user_doc = db["ghl_onboarding_test"].find_one({"user.email": email})
    if user_doc:
        return user_doc.get("user")
    return None


def load_craigslist_urls(**context):
    """Load Craigslist URLs from context conf or Airflow variable."""
    # Try to get from dag_run.conf first
    dag_run = context.get('dag_run')
    if dag_run and dag_run.conf and 'urls' in dag_run.conf:
        urls = dag_run.conf['urls']
        if isinstance(urls, str):
            urls = [url.strip() for url in urls.replace('\n', ',').split(',') if url.strip()]
        if urls:
            print(f"✓ Successfully loaded {len(urls)} URLs from DAG configuration")
            return urls
            
    # Try to get from Airflow variable fallback
    try:
        urls_raw = Variable.get("craigslist_target_url", default_var="")
        if urls_raw:
            urls = [url.strip() for url in urls_raw.replace('\n', ',').split(',') if url.strip()]
            if urls:
                print(f"✓ Successfully loaded {len(urls)} URLs from Airflow Variable 'craigslist_target_url'")
                return urls
    except Exception as e:
        print(f"Error loading craigslist_target_url variable: {e}")
    
    raise ValueError("No Craigslist URLs specified. Please set 'craigslist_target_url' Airflow Variable or provide in DAG conf.")


def extract_category_from_url(url: str) -> str:
    """Extract category name from Craigslist URL."""
    # Try to extract category code from URL
    match = re.search(r'/search/([a-z]+)', url)
    if match:
        return match.group(1)
    
    # Fallback: use last part of URL
    return url.rstrip('/').split('/')[-1]


def scrape_craigslist_url(category_url: str, category_name: str, url_index: int, **context):
    """
    Python callable to scrape a specific Craigslist URL.
    """
    from main import run_craigslist_scraper
    
    max_pages = int(Variable.get("craigslist_max_pages", default_var="5"))
    headless = Variable.get("craigslist_headless", default_var="true").lower() == "true"
    
    # Check for custom keywords in context
    dag_run = context.get('dag_run')
    custom_keywords = None
    if dag_run and dag_run.conf and 'keywords' in dag_run.conf:
        custom_keywords = dag_run.conf['keywords']
        print(f"Using custom keywords for intent detection: {custom_keywords}")

    print(f"Starting scrape for URL #{url_index + 1}: {category_name}")
    print(f"Target URL: {category_url}")
    print(f"Max pages: {max_pages}, Headless: {headless}")
    
    # Fetch user details
    user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    user_data = get_user_details(user_email) if user_email else None
    if user_data:
        print(f"✓ Linked to test user: {user_data.get('name')} ({user_email})")

    try:
        leads = run_craigslist_scraper(
            target=category_url,
            category=category_name,
            save_to_db=True,
            headless=headless,
            max_pages=max_pages,
            keywords=custom_keywords,
            user_data=user_data
        )
        
        print(f"✓ Successfully scraped {len(leads)} leads from {category_name}")
        return len(leads)
        
    except Exception as e:
        print(f"✗ Failed to scrape {category_name}: {e}")
        raise


# Define the DAG
dag = DAG(
    'craigslist_lead_scraper',
    default_args=default_args,
    description='Scrape service leads from Craigslist (multi-URL support)',
    schedule_interval='0 2 * * *',  # Run daily at 2 AM
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['scraping', 'craigslist', 'leads'],
    max_active_runs=1,
    max_active_tasks=1,
)

# Handle dynamic tasks based on configuration or variables
scraping_tasks = []

for idx in range(10): # Create 10 potential task slots
    task_id = f'scrape_craigslist_url_{idx + 1}'
    
    def dynamic_scrape_task(url_index, **context):
        urls = load_craigslist_urls(**context)
        if url_index >= len(urls):
            print(f"Skipping task {url_index + 1} as only {len(urls)} URLs provided.")
            return 0
        url = urls[url_index]
        category_name = extract_category_from_url(url)
        return scrape_craigslist_url(url, category_name, url_index, **context)

    task = PythonOperator(
        task_id=task_id,
        python_callable=dynamic_scrape_task,
        op_kwargs={'url_index': idx},
        provide_context=True,
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
