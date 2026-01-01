from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="test3",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["scraping"],
) as dag:

    BashOperator(
        task_id="test3",
        bash_command="python /opt/airflow/scraper/src/main.py",
        env={
            "MONGO_DB": "scraping",
            "JOB_NAME": "test3",
            "MONGO_URI": "mongodb://scraper:ScraperPasswordHere@mongo:27017/scraping?authSource=scraping",
        },
    )
