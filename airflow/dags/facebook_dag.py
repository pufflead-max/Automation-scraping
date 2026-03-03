"""
Airflow DAG for Facebook lead scraping with DYNAMIC task mapping.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import sys
import os
import json
from airflow_utils.callbacks import trigger_cookie_rotation

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
    from user_credential_manager import UserCredentialManager
    manager = UserCredentialManager()
    user_doc = manager.db.find_one(manager.collection, {"user.email": email})
    if user_doc:
        creds = manager.get_user_credentials(email)
        return {"user": user_doc.get("user"), "credentials": creds, "scraping_config": user_doc.get("scraping_config", {})}
    return None

def load_facebook_urls(**context):
    dag_run = context.get('dag_run')
    user_email_override = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
    
    from utils.mappings import get_mapping_manager
    mapper = get_mapping_manager()

    all_tasks = []
    if user_email_override:
        try:
            mappings = mapper.get_user_mappings(user_email_override)
        except Exception as e:
            print(f"⚠️ Failed to load mappings for {user_email_override}: {e}")
            mappings = []
        for m in mappings:
            fb_config = m.get("facebook", {})
            urls = fb_config.get("group_urls", []) + fb_config.get("page_urls", [])
            for url in urls:
                all_tasks.append({"target_data": {"url": url, "user_email": user_email_override, "vertical": m.get("vertical")}})
    else:
        from user_credential_manager import UserCredentialManager
        manager = UserCredentialManager()
        try:
            all_users = manager.db.find_many(manager.collection, {})
        except Exception as e:
            print(f"❌ Failed to fetch users from MongoDB: {e}")
            return []
        
        for user_doc in all_users:
            u_email = user_doc.get("user", {}).get("email")
            if not u_email:
                continue
            try:
                mappings = mapper.get_user_mappings(u_email)
            except Exception as e:
                # One bad user should never abort the entire load task
                print(f"⚠️ Skipping {u_email} — mapping lookup failed: {e}")
                continue
            for m in mappings:
                fb_config = m.get("facebook", {})
                urls = fb_config.get("group_urls", []) + fb_config.get("page_urls", [])
                for url in urls:
                    all_tasks.append({"target_data": {"url": url, "user_email": u_email, "vertical": m.get("vertical")}})
            
    print(f"✅ Loaded {len(all_tasks)} Facebook URL task(s)")
    return all_tasks

def scrape_facebook_url(target_data, **kwargs):
    from scrapers import FacebookScraper
    
    target_url = target_data.get('url')
    user_email = target_data.get('user_email')
    vertical_slug = target_data.get('vertical')

    user_details = get_user_details(user_email)
    if not user_details:
        print(f"⚠️ User details not found for {user_email}. Skipping.")
        return 0
    
    fb_onboarding = user_details.get("facebook", {})
    user_fb_config = user_details.get("scraping_config", {}).get("facebook", {}) if user_details else {}
    limit = int(user_fb_config.get("limit", Variable.get("facebook_post_limit", default_var=15)))
    # Forcing 15 if the variable returns 25 just as a precaution if it's not overriding
    if limit == 25: limit = 15
    headless = user_fb_config.get("headless", Variable.get("facebook_headless", default_var="true").lower() == "true")
    
    from utils.mappings import get_mapping_manager
    vertical_config = get_mapping_manager().get_vertical_config(vertical_slug) if vertical_slug else None
    
    if vertical_config:
        custom_keywords = vertical_config.get("keywords")
        exclude_keywords = vertical_config.get("exclude_keywords")
        custom_indicators = vertical_config.get("intent_indicators")
    else:
        custom_keywords = fb_onboarding.get("target_keywords") or user_fb_config.get("keywords")
        exclude_keywords = user_fb_config.get("exclude_keywords")
        custom_indicators = user_fb_config.get("intent_indicators")

    def to_list(val):
        if not val: return None
        if isinstance(val, list): return val
        return [k.strip() for k in str(val).replace(',', '\n').split('\n') if k.strip()]

    custom_keywords = to_list(custom_keywords)
    exclude_keywords = to_list(exclude_keywords)
    custom_indicators = to_list(custom_indicators)

    from user_credential_manager import UserCredentialManager
    manager = UserCredentialManager()
    owner_email = Variable.get("facebook_owner_email", default_var=os.getenv("FACEBOOK_EMAIL"))
    owner_password = Variable.get("facebook_owner_password", default_var=os.getenv("FACEBOOK_PASSWORD"))
    cookies = manager.load_cookies(owner_email, 'facebook') if owner_email else None
    user_data = user_details.get("user")

    scraper = FacebookScraper(cookies=cookies, headless=headless)
    results = scraper.run(
        target=target_url, limit=limit, save_to_db=True, 
        keywords=custom_keywords, exclude_keywords=exclude_keywords, 
        custom_indicators=custom_indicators, user_data=user_data,
        email=owner_email, password=owner_password
    )
    return len(results)

with DAG(
    'facebook_scraper_dag',
    default_args=default_args,
    description='Scrape Facebook pages with DYNAMIC mapping',
    schedule_interval='*/15 * * * *',
    catchup=False,
    tags=['scraping', 'facebook'],
    max_active_runs=1,
) as dag:

    load_urls_task = PythonOperator(
        task_id='load_facebook_urls',
        python_callable=load_facebook_urls,
        execution_timeout=timedelta(minutes=10),  # Fail cleanly before Airflow sends SIGTERM
    )

    scrape_task = PythonOperator.partial(
        task_id='scrape_facebook_url',
        python_callable=scrape_facebook_url,
        pool='scraper_pool',
        max_active_tis_per_dag=2, # Limit parallel workers to 2
    ).expand(
        op_kwargs=load_urls_task.output
    )
    
    def push_facebook_leads_to_ghl(**context):
        from push_leads import push_leads
        dag_run = context.get('dag_run')
        user_email = dag_run.conf.get('user_email') if dag_run and dag_run.conf else None
        push_leads(source="facebook", user_email=user_email)

    push_task = PythonOperator(
        task_id='push_facebook_to_ghl',
        python_callable=push_facebook_leads_to_ghl,
        provide_context=True,
    )
    
    def summarize_facebook_results(**context):
        from database import get_db_manager
        db = get_db_manager()
        yesterday = datetime.utcnow() - timedelta(days=1)
        jobs = db.find_many("scrape_jobs", {"scraper": "facebook", "started_at": {"$gte": yesterday}})
        total_items = sum(job.get('items_saved', 0) for job in jobs)
        successful_jobs = sum(1 for job in jobs if job.get('status') == 'completed')
        failed_jobs = sum(1 for job in jobs if job.get('status') == 'failed')
        return {'total_jobs': len(jobs), 'successful': successful_jobs, 'failed': failed_jobs, 'total_leads': total_items}

    summary_task = PythonOperator(
        task_id='summarize_results',
        python_callable=summarize_facebook_results,
        provide_context=True,
    )

    load_urls_task >> scrape_task >> push_task >> summary_task
