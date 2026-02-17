# airflow DAG
"""
Airflow DAG for Craigslist lead scraping with dynamic URL loading.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import os
import sys
import re
import json

sys.path.insert(0, '/opt/airflow/scraper/src')

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
    from pymongo import MongoClient
    mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017")
    client = MongoClient(mongo_uri)
    db = client["PUFF"]
    user_doc = db["users"].find_one({"user.email": email})
    return user_doc.get("user") if user_doc else None

def load_craigslist_urls(**context):
    dag_run = context.get('dag_run')
    user_email_override = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    
    if user_email_override:
        from pymongo import MongoClient
        mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017")
        client = MongoClient(mongo_uri)
        db = client["PUFF"]
        user_doc = db["users"].find_one({"user.email": user_email_override})
        
        if user_doc:
            cl_onboarding = user_doc.get("craigslist", {})
            urls = cl_onboarding.get("group_urls")
            
            if not urls:
                config = user_doc.get("scraping_config", {}).get("craigslist", {})
                urls = config.get("urls")
                
            if urls:
                if isinstance(urls, list): u_list = urls
                else: u_list = [url.strip() for url in urls.replace('\n', ',').split(',') if url.strip()]
                return [{"url": u, "user_email": user_email_override} for u in u_list]
            
    if dag_run and dag_run.conf and 'urls' in dag_run.conf:
        urls = dag_run.conf['urls']
        if isinstance(urls, str):
            urls = [url.strip() for url in urls.replace('\n', ',').split(',') if url.strip()]
        if urls: return [{"url": u, "user_email": user_email_override} for u in urls]
            
    # If no specific user requested, check if it's a manual run via Variable or scheduled run for ALL users
    try:
        urls_raw = Variable.get("craigslist_target_url", default_var="")
        if urls_raw:
            u_list = [url.strip() for url in urls_raw.replace('\n', ',').split(',') if url.strip()]
            if u_list: return [{"url": u, "user_email": None} for u in u_list] # Variable-based runs have no user context
    except:
        pass
    
    # Load ALL users for scheduled run
    if not user_email_override:
        from pymongo import MongoClient
        mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017")
        client = MongoClient(mongo_uri)
        db = client["PUFF"]
        
        all_users = db["users"].find({
            "$or": [
                {"craigslist.group_urls": {"$exists": True, "$ne": ""}},
                {"scraping_config.craigslist.urls": {"$exists": True}}
            ]
        })
        
        all_tasks = []
        for user_doc in all_users:
            u_email = user_doc.get("user", {}).get("email")
            if not u_email: continue
            
            cl_data = user_doc.get("craigslist", {})
            urls = cl_data.get("group_urls")
            
            u_list = []
            if urls:
                if isinstance(urls, list): u_list = urls
                else: u_list = [url.strip() for url in urls.replace('\n', ',').split(',') if url.strip()]
            
            if not u_list:
                conf_urls = user_doc.get("scraping_config", {}).get("craigslist", {}).get("urls")
                if conf_urls:
                    if isinstance(conf_urls, str):
                        u_list = [u.strip() for u in conf_urls.replace('\n', ',').split(',') if u.strip()]
                    else:
                        u_list = conf_urls
            
            for url in u_list:
                all_tasks.append({"url": url, "user_email": u_email})
        
        if all_tasks: return all_tasks

    raise ValueError("No Craigslist URLs found.")

def extract_category_from_url(url: str) -> str:
    match = re.search(r'/search/([a-z]+)', url)
    return match.group(1) if match else url.rstrip('/').split('/')[-1]

def scrape_craigslist_url(target_data, category_name: str, url_index: int, **context):
    from main import run_craigslist_scraper
    
    # Handle dict or string
    if isinstance(target_data, dict):
        category_url = target_data.get('url')
        user_email = target_data.get('user_email')
        # Re-extract category if needed or trust passed name (which might be wrong if url changed)
        # But category_name passed from dynamic_scrape_task depends on the url there.
    else:
        category_url = target_data
        dag_run = context.get('dag_run')
        user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None

    # Redetermine category_name to be safe if it came from a list index
    category_name = extract_category_from_url(category_url)

    max_pages = int(Variable.get("craigslist_max_pages", default_var="5"))
    headless = Variable.get("craigslist_headless", default_var="true").lower() == "true"
    
    custom_keywords = None
    
    # Load user specific config
    from pymongo import MongoClient
    mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017")
    client = MongoClient(mongo_uri)
    db = client["PUFF"]
    user_doc = db["users"].find_one({"user.email": user_email}) if user_email else None
    
    user_data = user_doc.get("user") if user_doc else None
    exclude_keywords = None
    custom_indicators = None
    
    if user_doc:
        cl_onboarding = user_doc.get("craigslist", {})
        custom_keywords = cl_onboarding.get("target_keywords")
        
        cl_config = user_doc.get("scraping_config", {}).get("craigslist", {})
        if not custom_keywords: custom_keywords = cl_config.get("keywords")
        
        exclude_keywords = cl_config.get("exclude_keywords")
        custom_indicators = cl_config.get("intent_indicators")
        max_pages = cl_config.get("max_pages", max_pages)

    # Defaults
    if not custom_keywords:
        custom_keywords = ["landscaping", "lawn care", "snow removal", "yard cleanup", "leaf removal"]

    dag_run = context.get('dag_run')
    if dag_run and dag_run.conf and dag_run.conf.get('user_email') == user_email:
        if 'keywords' in dag_run.conf: custom_keywords = dag_run.conf['keywords']
        if 'exclude_keywords' in dag_run.conf: exclude_keywords = dag_run.conf['exclude_keywords']
        if 'indicators' in dag_run.conf: custom_indicators = dag_run.conf['indicators']

    def to_list(val):
        if not val: return None
        if isinstance(val, list): return val
        return [k.strip() for k in str(val).replace(',', '\n').split('\n') if k.strip()]

    custom_keywords = to_list(custom_keywords)
    exclude_keywords = to_list(exclude_keywords)
    custom_indicators = to_list(custom_indicators)

    try:
        leads = run_craigslist_scraper(
            target=category_url,
            category=category_name,
            save_to_db=True,
            headless=headless,
            max_pages=max_pages,
            keywords=custom_keywords,
            exclude_keywords=exclude_keywords,
            custom_indicators=custom_indicators,
            user_data=user_data
        )
        return len(leads)
    except Exception as e:
        print(f"✗ Failed to scrape {category_name}: {e}")
        raise

dag = DAG(
    'craigslist_lead_scraper',
    default_args=default_args,
    description='Scrape service leads from Craigslist',
    schedule_interval='*/15 * * * *',
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['scraping', 'craigslist', 'leads'],
    max_active_runs=1,
)

scraping_tasks = []
for idx in range(10):
    task_id = f'scrape_craigslist_url_{idx + 1}'
    
    def dynamic_scrape_task(url_index, **context):
        urls = load_craigslist_urls(**context)
        if url_index >= len(urls): return 0
        url = urls[url_index]
        category_name = extract_category_from_url(url)
        return scrape_craigslist_url(url, category_name, url_index, **context)

    task = PythonOperator(
        task_id=task_id,
        python_callable=dynamic_scrape_task,
        op_kwargs={'url_index': idx},
        provide_context=True,
        dag=dag,
        pool='scraper_pool',
    )
    scraping_tasks.append(task)

def push_craigslist_leads_to_ghl():
    from push_leads import push_leads
    push_leads(source="craigslist")

push_task = PythonOperator(
    task_id='push_craigslist_to_ghl',
    python_callable=push_craigslist_leads_to_ghl,
    dag=dag,
)

def summarize_scraping_results(**context):
    from database import get_db_manager
    db = get_db_manager()
    yesterday = datetime.utcnow() - timedelta(days=1)
    jobs = db.find_many("scrape_jobs", {"scraper": "craigslist", "started_at": {"$gte": yesterday}})
    total_items = sum(job.get('items_saved', 0) for job in jobs)
    successful_jobs = sum(1 for job in jobs if job.get('status') == 'completed')
    failed_jobs = sum(1 for job in jobs if job.get('status') == 'failed')
    return {'total_jobs': len(jobs), 'successful': successful_jobs, 'failed': failed_jobs, 'total_leads': total_items}

summary_task = PythonOperator(
    task_id='summarize_results',
    python_callable=summarize_scraping_results,
    provide_context=True,
    dag=dag,
)

scraping_tasks >> push_task >> summary_task

