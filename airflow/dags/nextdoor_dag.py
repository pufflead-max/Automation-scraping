# airflow DAG
"""
Airflow DAG for Nextdoor lead scraping with dynamic URL loading.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json
from airflow_utils.callbacks import trigger_cookie_rotation

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
    from user_credential_manager import UserCredentialManager
    manager = UserCredentialManager()
    user_doc = manager.db.find_one(manager.collection, {"user.email": email})
    if user_doc:
        creds = manager.get_user_credentials(email)
        return {"user": user_doc.get("user"), "credentials": creds, "scraping_config": user_doc.get("scraping_config", {})}
    return None

def load_nextdoor_urls(**context):
    dag_run = context.get('dag_run')
    user_email_override = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    
    from utils.mappings import get_mapping_manager
    mapper = get_mapping_manager()

    if user_email_override:
        mappings = mapper.get_user_mappings(user_email_override)
        all_tasks = []
        for m in mappings:
            nd_config = m.get("nextdoor", {})
            urls = nd_config.get("group_urls", [])
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
            nd_config = m.get("nextdoor", {})
            urls = nd_config.get("group_urls", [])
            for url in urls:
                all_tasks.append({"url": url, "user_email": u_email, "vertical": m.get("vertical")})
            
    return all_tasks

def load_nextdoor_cookies():
    from user_credential_manager import UserCredentialManager
    manager = UserCredentialManager()
    
    owner_email = Variable.get("nextdoor_owner_email", default_var=os.getenv("NEXTDOOR_EMAIL"))
    cookies = manager.load_cookies(owner_email, 'nextdoor') if owner_email else None
    
    if cookies: return cookies

    cookies_json = os.getenv('NEXTDOOR_COOKIES')
    if cookies_json:
        try: return json.loads(cookies_json)
        except: pass
    
    try:
        cookies_str = Variable.get("nextdoor_cookies", default_var="")
        if cookies_str: return json.loads(cookies_str)
    except: pass
    
    return None

def scrape_nextdoor_url(target_data, url_index: int, default_max_pages: int = 5, **context):
    from main import run_nextdoor_scraper
    
    # Handle both direct URL string (legacy/single) or dict with user context
    if isinstance(target_data, dict):
        target_url = target_data.get('url')
        user_email = target_data.get('user_email')
    else:
        target_url = target_data
        dag_run = context.get('dag_run')
        user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None

    if not user_email: 
        print(f"⚠️ No user_email context for {target_url}. Skipping.")
        return 0

    user_details = get_user_details(user_email)
    if not user_details:
        print(f"⚠️ User details not found for {user_email}. Skipping.")
        return 0
    
    nd_onboarding = user_details.get("nextdoor", {})
    user_nd_config = user_details.get("scraping_config", {}).get("nextdoor", {}) if user_details else {}
    max_pages = user_nd_config.get("max_pages", default_max_pages)
    # Load keywords from Vertical Master List
    vertical_slug = target_data.get('vertical')
    from utils.mappings import get_mapping_manager
    vertical_config = get_mapping_manager().get_vertical_config(vertical_slug) if vertical_slug else None
    
    if vertical_config:
        custom_keywords = vertical_config.get("keywords")
    else:
        custom_keywords = nd_onboarding.get("target_keywords") or user_nd_config.get("keywords")

    try:
        user_data = user_details.get("user") if user_details else None
        cookies = load_nextdoor_cookies()
        
        leads = run_nextdoor_scraper(
            target=target_url,
            cookies=cookies,
            save_to_db=True,
            max_pages=max_pages,
            keywords=custom_keywords,
            user_data=user_data
        )
        return len(leads)
    except Exception as e:
        error_msg = str(e)
        if "session invalid" in error_msg.lower() or "cookie rotation required" in error_msg.lower():
            owner_email = Variable.get("nextdoor_owner_email", default_var=os.getenv("NEXTDOOR_EMAIL"))
            try:
                from airflow.api.common.trigger_dag import trigger_dag
                trigger_dag(
                    dag_id='nextdoor_multi_user_cookie_rotation',
                    run_id=f'auto_rotate_{datetime.now().strftime("%Y%m%d%H%M%S")}',
                    conf={'user_email': owner_email},
                    replace_microseconds=False
                )
            except: pass
        raise

with DAG(
    'nextdoor_lead_scraper',
    default_args=default_args,
    description='Scrape service leads from Nextdoor',
    schedule_interval='*/15 * * * *',
    catchup=False,
    tags=['scraping', 'nextdoor', 'leads'],
    max_active_runs=1,
) as dag:

    max_pages = int(Variable.get("nextdoor_max_pages", default_var="5"))
    scrape_tasks = []
    for idx in range(10):
        task_id = f'scrape_nextdoor_url_{idx + 1}'
        
        def dynamic_scrape_task(url_index, max_pages_val, **context):
            urls = load_nextdoor_urls(**context)
            if url_index >= len(urls): return 0
            return scrape_nextdoor_url(urls[url_index], url_index, max_pages_val, **context)

        task = PythonOperator(
            task_id=task_id,
            python_callable=dynamic_scrape_task,
            op_kwargs={'url_index': idx, 'max_pages_val': max_pages},
            provide_context=True,
            pool='scraper_pool',
        )
        scrape_tasks.append(task)

    def push_nextdoor_leads_to_ghl(**context):
        from push_leads import push_leads
        dag_run = context.get('dag_run')
        user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
        push_leads(source="nextdoor", user_email=user_email)

    push_task = PythonOperator(
        task_id='push_nextdoor_to_ghl',
        python_callable=push_nextdoor_leads_to_ghl,
        provide_context=True,
    )

    def summarize_nextdoor_results(**context):
        from database import get_db_manager
        db = get_db_manager()
        yesterday = datetime.utcnow() - timedelta(days=1)
        jobs = db.find_many("scrape_jobs", {"scraper": "nextdoor", "started_at": {"$gte": yesterday}})
        total_items = sum(job.get('items_saved', 0) for job in jobs)
        successful_jobs = sum(1 for job in jobs if job.get('status') == 'completed')
        failed_jobs = sum(1 for job in jobs if job.get('status') == 'failed')
        return {'total_jobs': len(jobs), 'successful': successful_jobs, 'failed': failed_jobs, 'total_leads': total_items}

    summary_task = PythonOperator(
        task_id='summarize_results',
        python_callable=summarize_nextdoor_results,
        provide_context=True,
    )

    scrape_tasks >> push_task >> summary_task

