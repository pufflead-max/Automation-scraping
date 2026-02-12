import json
import os
import sys

# Add Airflow to path if needed (usually handled by the environment)
try:
    from airflow.models import Variable
    from airflow.utils import db
except ImportError:
    print("Airflow not found in PYTHONPATH. Ensure this is run within an Airflow environment.")
    sys.exit(1)

def initialize():
    variables_file = "/opt/airflow/scripts/variables.json"
    
    if not os.path.exists(variables_file):
        print(f"Configuration file not found: {variables_file}")
        return

    with open(variables_file, 'r') as f:
        vars_to_set = json.load(f)

    print("Checking and initializing Airflow Variables...")
    
    # Define keys that represent secrets/credentials
    credential_keys = ["facebook_email", "facebook_password", "nextdoor_email", "nextdoor_password"]
    
    for key, value in vars_to_set.items():
        # Check if the value itself is an environment variable name
        env_val = os.getenv(value) if value in ["FACEBOOK_EMAIL", "FACEBOOK_PASSWORD", "NEXTDOOR_EMAIL", "NEXTDOOR_PASSWORD"] else None
        
        if env_val:
            value = env_val
            print(f"⚙️ Loaded '{key}' from environment variable.")

        try:
            # Check if variable already exists
            existing_val = Variable.get(key)
            
            # For credentials, if they are blank or default, update them
            if key in credential_keys and (not existing_val or existing_val in ["ENTER_YOUR_EMAIL", "ENTER_YOUR_PASSWORD", "FACEBOOK_EMAIL", "FACEBOOK_PASSWORD", "NEXTDOOR_EMAIL", "NEXTDOOR_PASSWORD"]):
                Variable.set(key, value)
                print(f"↻ Updated credential '{key}' in Airflow Variables.")
            else:
                print(f"✓ Variable '{key}' already exists. Skipping.")
        except Exception:
            # If it doesn't exist, create it
            Variable.set(key, value)
            print(f"+ Initialized Variable '{key}' with value.")

    # Initialize a pool for sequential scraping (1 slot)
    try:
        from airflow.models import Pool
        from airflow.utils.session import create_session
        
        with create_session() as session:
            pool = session.query(Pool).filter(Pool.pool == 'scraper_pool').first()
            if not pool:
                print("⚒ Creating 'scraper_pool' for sequential execution...")
                # include_deferred=False is required for Airflow 2.7+
                new_pool = Pool(
                    pool='scraper_pool', 
                    slots=1, 
                    description='Pool to ensure sequential scraping/browser tasks',
                    include_deferred=False
                )
                session.add(new_pool)
                session.commit()
            else:
                print("✓ 'scraper_pool' already exists.")
    except Exception as e:
        print(f"⚠️ Could not initialize pool: {e}")

if __name__ == "__main__":
    initialize()
