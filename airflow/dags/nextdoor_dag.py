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
    if dag_run and dag_run.conf and 'urls' in dag_run.conf:
        urls = dag_run.conf['urls']
        if isinstance(urls, str):
            urls = [url.strip() for url in urls.replace('\n', ',').split(',') if url.strip()]
        if urls: return urls

    user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    if not user_email: raise ValueError("No user_email provided.")

    user_details = get_user_details(user_email)
    if not user_details: raise ValueError(f"User details for {user_email} not found.")

    nd_onboarding = user_details.get("nextdoor", {})
    page_urls = nd_onboarding.get("page_urls", "")
    group_urls = nd_onboarding.get("group_urls", "")
    urls_list = []
    if page_urls: urls_list.extend([u.strip() for u in (page_urls.split(',') if isinstance(page_urls, str) else page_urls) if u.strip()])
    if group_urls: urls_list.extend([u.strip() for u in (group_urls.split(',') if isinstance(group_urls, str) else group_urls) if u.strip()])
    urls = urls_list

    if not urls:
        config = user_details.get("scraping_config", {}).get("nextdoor", {})
        urls = config.get("urls")
        
    if urls:
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.replace('\n', ',').split(',') if u.strip()]
        return urls

    raise ValueError(f"No Nextdoor URLs configured for user: {user_email}")

def load_nextdoor_cookies(user_details=None):
    if user_details:
        user_email = user_details.get("user", {}).get("email")
        if user_email:
            from user_credential_manager import UserCredentialManager
            manager = UserCredentialManager()
            cookies = manager.load_cookies(user_email, 'nextdoor')
            if cookies: return cookies

    cookies_json = os.getenv('NEXTDOOR_COOKIES')
    if cookies_json:
        try: return json.loads(cookies_json)
        except: pass
    
    try:
        cookies_str = Variable.get("nextdoor_cookies", default_var="")
        if cookies_str: return json.loads(cookies_str)
    except: pass
    
    raise ValueError("Nextdoor cookies not configured.")

def scrape_nextdoor_url(target_url: str, url_index: int, default_max_pages: int = 5, **context):
    from main import run_nextdoor_scraper
    dag_run = context.get('dag_run')
    user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    user_details = get_user_details(user_email) if user_email else None
    
    nd_onboarding = user_details.get("nextdoor", {})
    custom_keywords = nd_onboarding.get("target_keywords")
    
    user_nd_config = user_details.get("scraping_config", {}).get("nextdoor", {}) if user_details else {}
    max_pages = user_nd_config.get("max_pages", default_max_pages)
    
    if not custom_keywords: custom_keywords = user_nd_config.get("keywords")
    if dag_run and dag_run.conf and 'keywords' in dag_run.conf:
        custom_keywords = dag_run.conf['keywords']

    try:
        user_data = user_details.get("user") if user_details else None
        cookies = load_nextdoor_cookies(user_details)
        
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
            if user_email:
                try:
                    from airflow.api.common.trigger_dag import trigger_dag
                    trigger_dag(
                        dag_id='nextdoor_multi_user_cookie_rotation',
                        run_id=f'auto_rotate_{user_email.replace("@", "_")}_{datetime.now().strftime("%Y%m%d%H%M%S")}',
                        conf={'user_email': user_email},
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

