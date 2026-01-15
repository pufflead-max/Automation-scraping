"""
Smoke test DAG to verify scraper infrastructure is working.
This is a simple test that validates database connectivity and basic scraping setup.
"""

from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator
import os

# Get environment variables
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://scraper_admin:Mongodb_password12345@mongo:27017/PUFF?authSource=admin')

with DAG(
    dag_id="scrape_smoke_test",
    start_date=datetime(2026, 1, 15),
    schedule=None,  # Manual trigger only
    catchup=False,
    tags=["testing", "smoke-test"],
    description="Smoke test for scraper infrastructure"
) as dag:

    # Test 1: Verify Python environment
    test_python = BashOperator(
        task_id="test_python_environment",
        bash_command="python --version && pip list | grep -E '(selenium|beautifulsoup4|pymongo|pydantic)'",
    )
    
    # Test 2: Verify database connectivity
    test_database = BashOperator(
        task_id="test_database_connection",
        bash_command=f"""
python -c "
from pymongo import MongoClient
import sys

try:
    client = MongoClient('{MONGO_URI}', serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print('✓ Database connection successful')
    sys.exit(0)
except Exception as e:
    print(f'✗ Database connection failed: {{e}}')
    sys.exit(1)
"
        """,
    )
    
    # Test 3: Verify configuration loading
    test_config = BashOperator(
        task_id="test_configuration",
        bash_command="""
cd /opt/airflow/scraper/src && python -c "
from config import get_settings
import sys

try:
    settings = get_settings()
    print(f'✓ Configuration loaded successfully')
    print(f'  MongoDB: {settings.mongo_db}')
    print(f'  Log Level: {settings.log_level}')
    sys.exit(0)
except Exception as e:
    print(f'✗ Configuration loading failed: {e}')
    sys.exit(1)
"
        """,
    )
    
    # Test 4: Verify scraper imports
    test_imports = BashOperator(
        task_id="test_scraper_imports",
        bash_command="""
cd /opt/airflow/scraper/src && python -c "
import sys
try:
    from scrapers.craigslist import CraigslistScraper
    from models import CraigslistLead
    from database import get_db_manager
    print('✓ All scraper modules imported successfully')
    sys.exit(0)
except Exception as e:
    print(f'✗ Import failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"
        """,
    )
    
    # Set dependencies - run tests in sequence
    test_python >> test_database >> test_config >> test_imports

