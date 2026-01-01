from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="test2",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["scraping"],
) as dag:

    BashOperator(
        task_id="test2",
        bash_command="python /opt/airflow/scraper/src/main.py",
        env={
            "MONGO_DB": "scraping",
            "JOB_NAME": "airflow_smoke",
            "MONGO_URI": "mongodb://scraper:ScraperPasswordHere@mongo:27017/scraping?authSource=scraping",
        },
    )
