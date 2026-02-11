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
from airflow_utils.callbacks import trigger_cookie_rotation

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


def load_facebook_urls(**context):
    """Load Facebook URLs from context conf or Airflow variable."""
    # Try to get from dag_run.conf first (manual trigger with config)
    dag_run = context.get('dag_run')
    if dag_run and dag_run.conf and 'urls' in dag_run.conf:
        urls = dag_run.conf['urls']
        if isinstance(urls, str):
            urls = [url.strip() for url in urls.replace('\n', ',').split(',') if url.strip()]
        if urls:
            print(f"✓ Successfully loaded {len(urls)} URLs from DAG configuration")
            return urls

    # Fallback to Airflow variable
    try:
        urls_raw = Variable.get("facebook_target_url", default_var="")
        if urls_raw:
            urls = [url.strip() for url in urls_raw.replace('\n', ',').split(',') if url.strip()]
            if urls:
                print(f"✓ Successfully loaded {len(urls)} URLs from Airflow Variable 'facebook_target_url'")
                return urls
    except Exception as e:
        print(f"Error loading facebook_target_url variable: {e}")
    
    raise ValueError("No Facebook URLs specified. Please set 'facebook_target_url' Airflow Variable or provide in DAG conf.")


def scrape_facebook_url(target_url: str, url_index: int, **context):
    """
    Execute the Facebook scraper for a single URL.
    """
    from scrapers import FacebookScraper
    from utils.buyer_intent import BuyerIntentDetector
    
    # Load configuration
    limit = int(Variable.get("facebook_post_limit", default_var="25"))
    headless = Variable.get("facebook_headless", default_var="true").lower() == "true"
    
    # Check for custom keywords in context
    dag_run = context.get('dag_run')
    custom_keywords = None
    if dag_run and dag_run.conf and 'keywords' in dag_run.conf:
        custom_keywords = dag_run.conf['keywords']
        print(f"Using custom keywords for intent detection: {custom_keywords}")

    # Set custom keywords if provided
    if custom_keywords:
        # Note: This is an instance-level change if we modify the detector appropriately
        # For now, we'll pass it to the scraper run method if supported
        pass

    # Try to get cookies from variable
    cookies = None
    try:
        cookies_str = Variable.get("facebook_cookies", default_var="")
        if cookies_str:
            cookies = json.loads(cookies_str)
    except:
        print("Could not load cookies from Airflow Variable")

    # Fetch user details
    user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    user_data = get_user_details(user_email) if user_email else None
    if user_data:
        print(f"✓ Linked to test user: {user_data.get('name')} ({user_email})")

    print(f"Starting Facebook scrape for URL #{url_index + 1}: {target_url}")
    
    try:
        scraper = FacebookScraper(cookies=cookies, headless=headless)
        # Pass custom keywords and user_data to run
        results = scraper.run(
            target=target_url, 
            limit=limit, 
            save_to_db=True, 
            keywords=custom_keywords,
            user_data=user_data
        )
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
    max_active_runs=1,
    max_active_tasks=1,
) as dag:

    # Load URLs and create dynamic tasks
    # We use a trick to make load_facebook_urls accessible to the DAG structure
    # Actually, in a dynamic DAG, this might be tricky if it depends on context.
    # We'll use a fixed list or a variable for the skeleton, then tasks will handle the actual URL.
    
    # To support truly dynamic tasks based on conf, we need to handle the case where conf is not yet available during parsing.
    # For now, we'll try to get it from variable, and if it's a trigger, the tasks will use the conf.
    
    try:
        facebook_urls = [u for u in Variable.get("facebook_target_url", default_var="").replace('\n', ',').split(',') if u.strip()]
        if not facebook_urls:
            facebook_urls = ["https://www.facebook.com/marketplace"] # Default
    except:
        facebook_urls = ["https://www.facebook.com/marketplace"]

    scrape_tasks = []
    for idx in range(10): # Create 10 potential task slots
        task_id = f'scrape_facebook_url_{idx + 1}'
        
        def dynamic_scrape_task(url_index, **context):
            urls = load_facebook_urls(**context)
            if url_index >= len(urls):
                print(f"Skipping task {url_index + 1} as only {len(urls)} URLs provided.")
                return 0
            return scrape_facebook_url(urls[url_index], url_index, **context)

        task = PythonOperator(
            task_id=task_id,
            python_callable=dynamic_scrape_task,
            op_kwargs={'url_index': idx},
            provide_context=True,
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
