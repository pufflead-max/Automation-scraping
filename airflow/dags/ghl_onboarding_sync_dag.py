from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import sys
import os

sys.path.insert(0, '/opt/airflow/scraper/src')

default_args = {
    'owner': 'automation-scraping',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def sync_ghl_data():
    from scripts.ghl_onboarding_sync import sync_ghl_onboarding
    sync_ghl_onboarding()

with DAG(
    'ghl_onboarding_sync_dag',
    default_args=default_args,
    description='Sync client onboarding data from GHL to MongoDB',
    schedule_interval='@hourly',
    catchup=False,
    tags=['sync', 'ghl'],
) as dag:

    sync_task = PythonOperator(
        task_id='sync_ghl_to_mongodb',
        python_callable=sync_ghl_data,
    )

