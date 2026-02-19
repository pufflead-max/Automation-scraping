"""
Airflow DAG for system monitoring and health checks.
Runs periodically to check system health and send alerts if needed.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import sys

sys.path.insert(0, '/opt/airflow/scraper/src')

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'email_on_failure': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'system_monitoring',
    default_args=default_args,
    description='Monitor system health and performance',
    schedule_interval='*/30 * * * *',
    start_date=datetime(2026, 1, 15),
    catchup=False,
    tags=['monitoring', 'health-check'],
)


def check_system_health(**context):
    """Check overall system health."""
    from health import HealthChecker

    checker = HealthChecker()
    health = checker.get_overall()

    print(f"\n{'='*60}")
    print("SYSTEM HEALTH CHECK")
    print(f"{'='*60}")
    print(f"Overall Status: {health['status'].upper()}")
    print(f"Timestamp: {health['timestamp']}")
    print(f"\nDatabase: {health['checks']['db']['status']}")
    print(f"Jobs: {health['checks']['jobs']['status']}")
    print(f"{'='*60}\n")

    context['task_instance'].xcom_push(key='health_status', value=health['status'])

    if health['status'] == 'unhealthy':
        raise Exception("System is unhealthy! Check logs for details.")

    return health


def check_stale_jobs(**context):
    """Check for jobs that have been running too long (stuck jobs)."""
    from database import get_db_manager

    db = get_db_manager()
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
    else:
        print("✓ No stale jobs found")

    return len(stale_jobs)


def check_lead_counts(**context):
    """Check lead counts across all collections."""
    from database import get_db_manager

    db = get_db_manager()
    collections = ["Facebook_final_data", "Nextdoor_final_data", "Craigslist_final_data"]

    print(f"\n{'='*60}")
    print("LEAD COUNTS")
    print(f"{'='*60}")

    total = 0
    for col in collections:
        count = db.get_collection(col).count_documents({})
        unpushed = db.get_collection(col).count_documents({"pushed_to_ghl": {"$ne": True}})
        total += count
        print(f"  {col}: {count} total, {unpushed} unpushed")

    print(f"  Total: {total}")
    print(f"{'='*60}\n")
    return total


health_check_task = PythonOperator(
    task_id='check_system_health',
    python_callable=check_system_health,
    provide_context=True,
    dag=dag,
)

stale_jobs_task = PythonOperator(
    task_id='check_stale_jobs',
    python_callable=check_stale_jobs,
    provide_context=True,
    dag=dag,
)

lead_counts_task = PythonOperator(
    task_id='check_lead_counts',
    python_callable=check_lead_counts,
    provide_context=True,
    dag=dag,
)

health_check_task >> [stale_jobs_task, lead_counts_task]
