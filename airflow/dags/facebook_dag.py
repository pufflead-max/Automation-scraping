"""
Airflow DAG for Facebook lead scraping with dynamic URL loading.
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
    
    # If specific user requested, load only theirs
    if user_email_override:
        user_details = get_user_details(user_email_override)
        if not user_details: raise ValueError(f"User details for {user_email_override} not found.")
        
        fb_onboarding = user_details.get("facebook", {})
        page_urls = fb_onboarding.get("page_urls", "")
        group_urls = fb_onboarding.get("group_urls", "")
        
        urls = []
        if page_urls: urls.extend([u.strip() for u in (page_urls.split(',') if isinstance(page_urls, str) else page_urls) if u.strip()])
        if group_urls: urls.extend([u.strip() for u in (group_urls.split(',') if isinstance(group_urls, str) else group_urls) if u.strip()])
        
        if not urls:
             config = user_details.get("scraping_config", {}).get("facebook", {})
             urls = config.get("urls")
        
        if urls and isinstance(urls, str):
             urls = [u.strip() for u in urls.replace('\n', ',').split(',') if u.strip()]
             
        return [{"url": u, "user_email": user_email_override} for u in urls or []]

    # Otherwise, load ALL users
    from user_credential_manager import UserCredentialManager
    manager = UserCredentialManager()
    # Find all users with Facebook URLs configured
    # We look for users who have 'facebook.page_urls' or 'facebook.group_urls'
    all_users = manager.db.find_many(manager.collection, {
        "$or": [
            {"facebook.page_urls": {"$exists": True, "$ne": ""}},
            {"facebook.group_urls": {"$exists": True, "$ne": ""}},
            {"scraping_config.facebook.urls": {"$exists": True}}
        ]
    })
    
    all_tasks = []
    for user_doc in all_users:
        u_email = user_doc.get("user", {}).get("email")
        if not u_email: continue
        
        fb_data = user_doc.get("facebook", {})
        p_urls = fb_data.get("page_urls", "")
        g_urls = fb_data.get("group_urls", "")
        
        u_list = []
        if p_urls: u_list.extend([u.strip() for u in (p_urls.split(',') if isinstance(p_urls, str) else p_urls) if u.strip()])
        if g_urls: u_list.extend([u.strip() for u in (g_urls.split(',') if isinstance(g_urls, str) else g_urls) if u.strip()])
        
        if not u_list:
            conf_urls = user_doc.get("scraping_config", {}).get("facebook", {}).get("urls")
            if conf_urls:
                 if isinstance(conf_urls, str):
                     u_list = [u.strip() for u in conf_urls.replace('\n', ',').split(',') if u.strip()]
                 else:
                     u_list = conf_urls
        
        for url in u_list:
            all_tasks.append({"url": url, "user_email": u_email})
            
    return all_tasks

def scrape_facebook_url(target_data, url_index: int, **context):
    from scrapers import FacebookScraper
    
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
    
    fb_onboarding = user_details.get("facebook", {})
    custom_keywords = fb_onboarding.get("target_keywords")
    fb_email = fb_onboarding.get("email")
    fb_password = fb_onboarding.get("password")
    
    user_fb_config = user_details.get("scraping_config", {}).get("facebook", {}) if user_details else {}
    limit = int(user_fb_config.get("limit", Variable.get("facebook_post_limit", default_var="25")))
    headless = user_fb_config.get("headless", Variable.get("facebook_headless", default_var="true").lower() == "true")
    
    if not custom_keywords: custom_keywords = user_fb_config.get("keywords")
    exclude_keywords = user_fb_config.get("exclude_keywords")
    custom_indicators = user_fb_config.get("intent_indicators")
    
    # Allow DAG run override only if it's a specific single-user run
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

    cookies = None
    if user_details:
        user_data = user_details.get("user")
        from user_credential_manager import UserCredentialManager
        manager = UserCredentialManager()
        cookies = manager.load_cookies(user_email, 'facebook')
        fb_creds = user_details.get("credentials", {}).get("facebook", {})
        fb_email = fb_creds.get("email") or fb_email
        fb_password = fb_creds.get("password") or fb_password
    else:
        user_data = None

    try:
        scraper = FacebookScraper(cookies=cookies, headless=headless)
        results = scraper.run(
            target=target_url, 
            limit=limit, 
            save_to_db=True, 
            keywords=custom_keywords,
            exclude_keywords=exclude_keywords,
            custom_indicators=custom_indicators,
            user_data=user_data,
            email=fb_email,
            password=fb_password
        )
        return len(results)
    except Exception as e:
        error_msg = str(e)
        if "authentication failed" in error_msg.lower() or "session invalid" in error_msg.lower():
            if user_email:
                try:
                    from airflow.api.common.trigger_dag import trigger_dag
                    trigger_dag(
                        dag_id='facebook_multi_user_cookie_rotation',
                        run_id=f'auto_rotate_fb_{user_email.replace("@", "_")}_{datetime.now().strftime("%Y%m%d%H%M%S")}',
                        conf={'user_email': user_email},
                        replace_microseconds=False
                    )
                except: pass
        raise

with DAG(
    'facebook_scraper_dag',
    default_args=default_args,
    description='Scrape Facebook pages',
    schedule_interval='*/15 * * * *',
    catchup=False,
    tags=['scraping', 'facebook'],
    max_active_runs=1,
) as dag:

    scrape_tasks = []
    for idx in range(10):
        task_id = f'scrape_facebook_url_{idx + 1}'
        
        def dynamic_scrape_task(url_index, **context):
            urls = load_facebook_urls(**context)
            if url_index >= len(urls): return 0
            return scrape_facebook_url(urls[url_index], url_index, **context)

        task = PythonOperator(
            task_id=task_id,
            python_callable=dynamic_scrape_task,
            op_kwargs={'url_index': idx},
            provide_context=True,
            pool='scraper_pool',
        )
        scrape_tasks.append(task)
    
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

    scrape_tasks >> push_task >> summary_task
