"""
Airflow DAG for Facebook lead scraping with Dynamic Task Mapping.
Logic: 
1. Load URLs from User data in MongoDB.
2. Scrape each URL in parallel (mapped tasks).
3. Synchronize found leads to MongoDB, then GHL and Google Sheets.
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
            for m in mappings:
                fb_config = m.get("facebook", {})
                urls = fb_config.get("group_urls", []) + fb_config.get("page_urls", [])
                for url in urls:
                    all_tasks.append({"target_data": {"url": url, "user_email": user_email_override, "vertical": m.get("vertical")}})
        except Exception as e:
            print(f"⚠️ Failed to load mappings for {user_email_override}: {e}")
    else:
        from user_credential_manager import UserCredentialManager
        manager = UserCredentialManager()
        try:
            all_users = manager.db.find_many(manager.collection, {})
            
            for user_doc in all_users:
                u_email = user_doc.get("user", {}).get("email")
                if not u_email: continue
                try:
                    mappings = mapper.get_user_mappings(u_email)
                    for m in mappings:
                        fb_config = m.get("facebook", {})
                        urls = fb_config.get("group_urls", []) + fb_config.get("page_urls", [])
                        for url in urls:
                            all_tasks.append({"target_data": {"url": url, "user_email": u_email, "vertical": m.get("vertical")}})
                except Exception as e:
                    print(f"⚠️ Skipping {u_email}: {e}")
        except Exception as e:
            print(f"❌ Failed to fetch users: {e}")
            return []
            
    print(f"✅ Loaded {len(all_tasks)} Facebook task(s)")
    return all_tasks

def scrape_facebook_url(target_data, **kwargs):
    from scrapers import FacebookScraper
    
    target_url = target_data.get('url')
    user_email = target_data.get('user_email')
    vertical_slug = target_data.get('vertical')

    user_details = get_user_details(user_email)
    if not user_details:
        print(f"⚠️ User details not found for {user_email}.")
        return 0
    
    fb_config = user_details.get("scraping_config", {}).get("facebook", {})
    limit = int(fb_config.get("limit", Variable.get("facebook_post_limit", default_var=15)))
    headless = fb_config.get("headless", Variable.get("facebook_headless", default_var="true").lower() == "true")
    
    from utils.mappings import get_mapping_manager
    vertical_config = get_mapping_manager().get_vertical_config(vertical_slug) if vertical_slug else None
    
    if vertical_config:
        kw_list = vertical_config.get("keywords")
        ex_list = vertical_config.get("exclude_keywords")
        ind_list = vertical_config.get("intent_indicators")
    else:
        kw_list = user_details.get("facebook", {}).get("target_keywords") or fb_config.get("keywords")
        ex_list = fb_config.get("exclude_keywords")
        ind_list = fb_config.get("intent_indicators")

    def to_list(val):
        if not val: return None
        if isinstance(val, list): return val
        return [k.strip() for k in str(val).replace(',', '\n').split('\n') if k.strip()]

    from user_credential_manager import UserCredentialManager
    mgr = UserCredentialManager()
    owner_email = Variable.get("facebook_owner_email", default_var=os.getenv("FACEBOOK_EMAIL"))
    owner_pw = Variable.get("facebook_owner_password", default_var=os.getenv("FACEBOOK_PASSWORD"))
    cookies = mgr.load_cookies(owner_email, 'facebook') if owner_email else None

    # Step: Execute Scraper
    scraper = FacebookScraper(cookies=cookies, headless=headless)
    results = scraper.run(
        target=target_url, 
        limit=limit, 
        save_to_db=True, 
        keywords=to_list(kw_list), 
        exclude_keywords=to_list(ex_list), 
        custom_indicators=to_list(ind_list), 
        user_data=user_details,
        email=owner_email, 
        password=owner_pw
    )
    return len(results)

with DAG(
    'facebook_scraper_dag',
    default_args=default_args,
    description='Scrape Facebook periodically with multi-user support',
    schedule_interval='*/15 * * * *',
    catchup=False,
    tags=['production', 'facebook'],
    max_active_runs=1,
) as dag:

    load_urls = PythonOperator(
        task_id='load_facebook_urls',
        python_callable=load_facebook_urls,
    )

    scrape_urls = PythonOperator.partial(
        task_id='scrape_facebook_url',
        python_callable=scrape_facebook_url,
        pool='scraper_pool',
        max_active_tis_per_dag=2,
    ).expand(
        op_kwargs=load_urls.output
    )
    
    def sync_and_push(**context):
        from push_leads import push_leads
        user_email = context.get('dag_run').conf.get('user_email') if context.get('dag_run') else None
        push_leads(source="facebook", user_email=user_email)

    push_to_integrations = PythonOperator(
        task_id='push_to_ghl_and_sheets',
        python_callable=sync_and_push,
    )
    
    def summarize_runs(**context):
        from database import get_db_manager
        db = get_db_manager()
        yesterday = datetime.utcnow() - timedelta(days=1)
        jobs = db.find_many("scrape_jobs", {"scraper": "facebook", "started_at": {"$gte": yesterday}})
        total_leads = sum(job.get('items_saved', 0) for job in jobs)
        return {'jobs': len(jobs), 'total_leads': total_leads}

    summary = PythonOperator(
        task_id='summarize_results',
        python_callable=summarize_runs,
    )

    load_urls >> scrape_urls >> push_to_integrations >> summary
