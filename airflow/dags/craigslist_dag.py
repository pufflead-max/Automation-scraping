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
    from database import get_db_manager
    db = get_db_manager()
    user_doc = db.find_one("users", {"user.email": email})
    return user_doc.get("user") if user_doc else None

def load_craigslist_urls(**context):
    dag_run = context.get('dag_run')
    user_email_override = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    
    from utils.mappings import get_mapping_manager
    mapper = get_mapping_manager()

    if user_email_override:
        mappings = mapper.get_user_mappings(user_email_override)
        all_tasks = []
        for m in mappings:
            cl_config = m.get("craigslist", {})
            urls = cl_config.get("urls", [])
            for url in urls:
                all_tasks.append({"url": url, "user_email": user_email_override, "vertical": m.get("vertical")})
        return all_tasks

    # Load ALL users
    from user_credential_manager import UserCredentialManager
    manager = UserCredentialManager()
    all_users = manager.db.find_many(manager.collection, {})

    all_tasks = []
    for user_doc in all_users:
        u_email = user_doc.get("user", {}).get("email")
        if not u_email: continue
        
        mappings = mapper.get_user_mappings(u_email)
        for m in mappings:
            cl_config = m.get("craigslist", {})
            urls = cl_config.get("urls", [])
            for url in urls:
                all_tasks.append({"url": url, "user_email": u_email, "vertical": m.get("vertical")})
            
    return all_tasks

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
    from database import get_db_manager
    db = get_db_manager()
    user_doc = db.find_one("users", {"user.email": user_email}) if user_email else None
    
    user_data = user_doc.get("user") if user_doc else None
    exclude_keywords = None
    custom_indicators = None
    
    # Load keywords from Vertical Master List
    vertical_slug = target_data.get('vertical')
    from utils.mappings import get_mapping_manager
    vertical_config = get_mapping_manager().get_vertical_config(vertical_slug) if vertical_slug else None
    
    if vertical_config:
        custom_keywords = vertical_config.get("keywords")
        exclude_keywords = vertical_config.get("exclude_keywords")
        custom_indicators = vertical_config.get("intent_indicators")
    else:
        cl_onboarding = user_doc.get("craigslist", {})
        custom_keywords = cl_onboarding.get("target_keywords")
        cl_config = user_doc.get("scraping_config", {}).get("craigslist", {})
        if not custom_keywords: custom_keywords = cl_config.get("keywords")
        exclude_keywords = cl_config.get("exclude_keywords")
        custom_indicators = cl_config.get("intent_indicators")

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
        url_data = urls[url_index]
        url_str = url_data.get('url') if isinstance(url_data, dict) else url_data
        category_name = extract_category_from_url(url_str)
        return scrape_craigslist_url(url_data, category_name, url_index, **context)

    task = PythonOperator(
        task_id=task_id,
        python_callable=dynamic_scrape_task,
        op_kwargs={'url_index': idx},
        provide_context=True,
        dag=dag,
        pool='scraper_pool',
    )
    scraping_tasks.append(task)

def push_craigslist_leads_to_ghl(**context):
    from push_leads import push_leads
    dag_run = context.get('dag_run')
    user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    push_leads(source="craigslist", user_email=user_email)

push_task = PythonOperator(
    task_id='push_craigslist_to_ghl',
    python_callable=push_craigslist_leads_to_ghl,
    provide_context=True,
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

