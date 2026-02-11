# airflow DAG
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
from airflow_utils.callbacks import trigger_cookie_rotation

# Add scraper src to path
sys.path.insert(0, '/opt/airflow/scraper/src')

default_args = {
    'owner': 'automation-scraping',
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=1),
    'on_failure_callback': trigger_cookie_rotation,
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


def load_nextdoor_urls(**context):
    """Load Nextdoor URLs from context conf or Airflow variable."""
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
        urls_raw = Variable.get("nextdoor_target_url", default_var="")
        if urls_raw:
            urls = [url.strip() for url in urls_raw.replace('\n', ',').split(',') if url.strip()]
            if urls:
                print(f"✓ Successfully loaded {len(urls)} URLs from Airflow Variable 'nextdoor_target_url'")
                return urls
    except Exception as e:
        print(f"Error loading nextdoor_target_url variable: {e}")
    
    raise ValueError("No Nextdoor URLs specified. Please set 'nextdoor_target_url' Airflow Variable or provide in DAG conf.")


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
        except json.JSONDecodeError:
            print("Could not parse NEXTDOOR_COOKIES environment variable as JSON.")
        except Exception as e:
            print(f"An unexpected error occurred loading NEXTDOOR_COOKIES env var: {e}")
    
    # Try to load from Airflow variable as fallback for env
    try:
        cookies_str = Variable.get("nextdoor_cookies", default_var="")
        if cookies_str:
            return json.loads(cookies_str)
    except json.JSONDecodeError:
        print("Could not parse 'nextdoor_cookies' Airflow Variable as JSON.")
    except Exception as e:
        print(f"An unexpected error occurred loading 'nextdoor_cookies' Airflow Variable: {e}")
    
    raise ValueError(
        "Nextdoor cookies not configured. "
        "Set NEXTDOOR_COOKIES env var or nextdoor_cookies Airflow Var."
    )


def scrape_nextdoor_url(target_url: str, url_index: int, max_pages: int = 5, **context):
    """
    Python callable to scrape a specific Nextdoor URL.
    """
    from main import run_nextdoor_scraper
    
    print(f"Starting Nextdoor scrape for URL #{url_index + 1}: {target_url}")
    print(f"Max pages: {max_pages}")
    
    # Check for custom keywords in context
    dag_run = context.get('dag_run')
    custom_keywords = None
    if dag_run and dag_run.conf and 'keywords' in dag_run.conf:
        custom_keywords = dag_run.conf['keywords']
        print(f"Using custom keywords for intent detection: {custom_keywords}")

    try:
        # Load cookies
        cookies = load_nextdoor_cookies()
        print(f"✓ Loaded cookies")
        
        # Fetch user details
        user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
        user_data = get_user_details(user_email) if user_email else None
        if user_data:
            print(f"✓ Linked to test user: {user_data.get('name')} ({user_email})")

        # Run scraper
        leads = run_nextdoor_scraper(
            target=target_url,
            cookies=cookies,
            save_to_db=True,
            max_pages=max_pages,
            keywords=custom_keywords,
            user_data=user_data
        )
        
        print(f"✓ Successfully scraped {len(leads)} leads from {target_url}")
        return len(leads)
        
    except Exception as e:
        print(f"✗ Failed to scrape Nextdoor {target_url}: {e}")
        raise


# Define the DAG
with DAG(
    'nextdoor_lead_scraper',
    default_args=default_args,
    description='Scrape service leads from Nextdoor (multi-URL support)',
    schedule_interval='@daily',
    catchup=False,
    tags=['scraping', 'nextdoor', 'leads'],
    max_active_runs=1,
    max_active_tasks=1,
) as dag:

    # To support truly dynamic tasks based on conf, we use a fixed number of task slots
    # each checking if an actual URL is provided in the configuration.
    
    max_pages = int(Variable.get("nextdoor_max_pages", default_var="5"))
    
    scrape_tasks = []
    for idx in range(10): # Create 10 potential task slots
        task_id = f'scrape_nextdoor_url_{idx + 1}'
        
        def dynamic_scrape_task(url_index, max_pages_val, **context):
            urls = load_nextdoor_urls(**context)
            if url_index >= len(urls):
                print(f"Skipping task {url_index + 1} as only {len(urls)} URLs provided.")
                return 0
            return scrape_nextdoor_url(urls[url_index], url_index, max_pages_val, **context)

        task = PythonOperator(
            task_id=task_id,
            python_callable=dynamic_scrape_task,
            op_kwargs={'url_index': idx, 'max_pages_val': max_pages},
            provide_context=True,
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
