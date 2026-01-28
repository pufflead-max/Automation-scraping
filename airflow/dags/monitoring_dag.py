"""
Airflow DAG for system monitoring and health checks.
Runs periodically to check system health and send alerts if needed.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import sys

# Add scraper src to path
sys.path.insert(0, '/opt/airflow/scraper/src')

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'email_on_failure': True,  # Enable when email is configured
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'system_monitoring',
    default_args=default_args,
    description='Monitor system health and performance',
    schedule_interval='*/30 * * * *',  # Every 30 minutes
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['monitoring', 'health-check'],
)


def check_system_health(**context):
    """
    Check overall system health.
    """
    from health import HealthChecker
    
    checker = HealthChecker()
    health = checker.get_overall_health()
    
    print("\n" + "="*60)
    print("SYSTEM HEALTH CHECK")
    print("="*60)
    print(f"Overall Status: {health['status'].upper()}")
    print(f"Timestamp: {health['timestamp']}")
    print("\nDatabase:")
    print(f"  Status: {health['checks']['database']['status']}")
    print(f"  Connected: {health['checks']['database'].get('connected', 'N/A')}")
    print("\nRecent Jobs (24h):")
    print(f"  Status: {health['checks']['recent_jobs']['status']}")
    print(f"  Total: {health['checks']['recent_jobs'].get('total_jobs', 0)}")
    print(f"  Success Rate: {health['checks']['recent_jobs'].get('success_rate_percent', 0)}%")
    print("\nData Freshness:")
    print(f"  Status: {health['checks']['data_freshness']['status']}")
    print(f"  Recent Leads: {health['checks']['data_freshness'].get('recent_leads_count', 0)}")
    print("="*60 + "\n")
    
    # Push to XCom for downstream tasks
    context['task_instance'].xcom_push(key='health_status', value=health['status'])
    
    # Raise alert if unhealthy
    if health['status'] == 'unhealthy':
        raise Exception(f"System is unhealthy! Check logs for details.")
    
    return health


def collect_metrics(**context):
    """
    Collect and log system metrics.
    """
    from health import get_system_metrics
    
    metrics = get_system_metrics()
    
    print("\n" + "="*60)
    print("SYSTEM METRICS")
    print("="*60)
    print(f"Total Leads: {metrics.get('total_leads', 0)}")
    print(f"Total Jobs: {metrics.get('total_jobs', 0)}")
    print("\nLeads by Source:")
    for source, count in metrics.get('leads_by_source', {}).items():
        print(f"  {source}: {count}")
    print("\nLeads by Category:")
    for category, count in list(metrics.get('leads_by_category', {}).items())[:10]:
        print(f"  {category}: {count}")
    print("\nLast 7 Days:")
    print(f"  Total Jobs: {metrics['last_7_days'].get('total_jobs', 0)}")
    print(f"  Success Rate: {metrics['last_7_days'].get('success_rate_percent', 0)}%")
    print("="*60 + "\n")
    
    return metrics


def check_stale_jobs(**context):
    """
    Check for jobs that have been running too long (stuck jobs).
    """
    from database import get_db_manager
    from datetime import datetime, timedelta
    
    db = get_db_manager()
    
    # Find jobs that started more than 2 hours ago and are still "running"
    cutoff = datetime.utcnow() - timedelta(hours=2)
    
    stale_jobs = db.find_many(
        "scrape_jobs",
        {
            "status": {"$in": ["started", "running"]},
            "started_at": {"$lt": cutoff}
        }
    )
    
    if stale_jobs:
        print(f"\n⚠️  WARNING: Found {len(stale_jobs)} stale jobs!")
        for job in stale_jobs:
            print(f"  - Job {job['job_id']}: {job['scraper']} (started {job['started_at']})")
        
        # Could update these to "failed" status
        # for job in stale_jobs:
        #     db.update_one(
        #         "scrape_jobs",
        #         {"job_id": job['job_id']},
        #         {"$set": {"status": "failed", "error_message": "Job timed out"}}
        #     )
    else:
        print("✓ No stale jobs found")
    
    return len(stale_jobs)


# Define tasks
health_check_task = PythonOperator(
    task_id='check_system_health',
    python_callable=check_system_health,
    provide_context=True,
    dag=dag,
)

metrics_task = PythonOperator(
    task_id='collect_metrics',
    python_callable=collect_metrics,
    provide_context=True,
    dag=dag,
)

stale_jobs_task = PythonOperator(
    task_id='check_stale_jobs',
    python_callable=check_stale_jobs,
    provide_context=True,
    dag=dag,
)

# Set dependencies - all run in parallel
[health_check_task, metrics_task, stale_jobs_task]
