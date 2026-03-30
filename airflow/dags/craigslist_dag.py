"""
Airflow DAG for Craigslist lead scraping with DYNAMIC task mapping.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import os
import sys
import re

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

def load_craigslist_urls(**context):
    dag_run = context.get('dag_run')
    # Hardcoded per request to target only one user
    user_email_override = "pnm.lnweb@yopmail.com"
    
    from utils.mappings import get_mapping_manager
    mapper = get_mapping_manager()

    all_tasks = []
    if user_email_override:
        mappings = mapper.get_user_mappings(user_email_override)
        for m in mappings:
            cl_config = m.get("craigslist", {})
            urls = cl_config.get("urls", [])
            for url in urls:
                all_tasks.append({"target_data": {"url": url, "user_email": user_email_override, "vertical": m.get("vertical")}})
    else:
        from user_credential_manager import UserCredentialManager
        manager = UserCredentialManager()
        
        all_users = manager.db.find_many(manager.collection, {})

        for user_doc in all_users:
            u_email = user_doc.get("user", {}).get("email")
            if not u_email: continue
            
            mappings = mapper.get_user_mappings(u_email)
            for m in mappings:
                cl_config = m.get("craigslist", {})
                urls = cl_config.get("urls", [])
                for url in urls:
                    all_tasks.append({"target_data": {"url": url, "user_email": u_email, "vertical": m.get("vertical")}})
            
    return all_tasks

def extract_category_from_url(url: str) -> str:
    match = re.search(r'/search/([a-z]+)', url)
    return match.group(1) if match else url.rstrip('/').split('/')[-1]

def scrape_craigslist_url(target_data, **kwargs):
    from main import run_craigslist_scraper
    
    category_url = target_data.get('url')
    user_email = target_data.get('user_email')
    vertical_slug = target_data.get('vertical')

    category_name = extract_category_from_url(category_url)
    max_pages = int(Variable.get("craigslist_max_pages", default_var="5"))
    headless = Variable.get("craigslist_headless", default_var="true").lower() == "true"
    
    from database import get_db_manager
    db = get_db_manager()
    user_doc = db.find_one("users", {"user.email": user_email}) if user_email else None
    user_data = user_doc.get("user") if user_doc else None
    
    from utils.mappings import get_mapping_manager
    vertical_config = get_mapping_manager().get_vertical_config(vertical_slug) if vertical_slug else None
    
    if vertical_config:
        custom_keywords = vertical_config.get("keywords")
        exclude_keywords = vertical_config.get("exclude_keywords")
        custom_indicators = vertical_config.get("intent_indicators")
    else:
        cl_onboarding = user_doc.get("craigslist", {}) if user_doc else {}
        custom_keywords = cl_onboarding.get("target_keywords")
        cl_config = user_doc.get("scraping_config", {}).get("craigslist", {}) if user_doc else {}
        if not custom_keywords: custom_keywords = cl_config.get("keywords")
        exclude_keywords = cl_config.get("exclude_keywords")
        custom_indicators = cl_config.get("intent_indicators")

    if not custom_keywords:
        custom_keywords = ["landscaping", "lawn care", "snow removal", "yard cleanup", "leaf removal"]

    def to_list(val):
        if not val: return None
        if isinstance(val, list): return val
        return [k.strip() for k in str(val).replace(',', '\n').split('\n') if k.strip()]

    custom_keywords = to_list(custom_keywords)
    exclude_keywords = to_list(exclude_keywords)
    custom_indicators = to_list(custom_indicators)

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

with DAG(
    'craigslist_lead_scraper',
    default_args=default_args,
    description='Scrape service leads from Craigslist',
    schedule_interval='*/15 * * * *',
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['scraping', 'craigslist', 'leads'],
    max_active_runs=1,
) as dag:

    load_urls_task = PythonOperator(
        task_id='load_craigslist_urls',
        python_callable=load_craigslist_urls,
    )

    scrape_task = PythonOperator.partial(
        task_id='scrape_craigslist_url',
        python_callable=scrape_craigslist_url,
        pool='scraper_pool',
    ).expand(
        op_kwargs=load_urls_task.output
    )

    def push_craigslist_leads_to_ghl(**context):
        from push_leads import push_leads
        dag_run = context.get('dag_run')
        user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
        push_leads(source="craigslist", user_email=user_email)

    push_task = PythonOperator(
        task_id='push_craigslist_to_ghl',
        python_callable=push_craigslist_leads_to_ghl,
        provide_context=True,
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
    )

    load_urls_task >> scrape_task >> push_task >> summary_task
