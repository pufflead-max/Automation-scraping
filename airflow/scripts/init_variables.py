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
            print(f" Loaded '{key}' from environment variable.")

        try:
            # Check if variable already exists
            existing_val = Variable.get(key)

            # For credentials, if they are blank or default, update them
            if key in credential_keys and (not existing_val or existing_val in ["ENTER_YOUR_EMAIL", "ENTER_YOUR_PASSWORD", "FACEBOOK_EMAIL", "FACEBOOK_PASSWORD", "NEXTDOOR_EMAIL", "NEXTDOOR_PASSWORD"]):
                Variable.set(key, value)
                print(f"↻ Updated credential '{key}' in Airflow Variables.")
            else:
                print(f" Variable '{key}' already exists. Skipping.")
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
                print(" Creating 'scraper_pool' for sequential execution...")
                # include_deferred=False is required for Airflow 2.7+
                new_pool = Pool(
                    pool='scraper_pool',
                    slots=3,
                    description='Pool to allow concurrent scraping/browser tasks (CL, FB, ND)',
                    include_deferred=False
                )
                session.add(new_pool)
                session.commit()
            else:
                if pool.slots != 3:
                    print(f"↻ Updating 'scraper_pool' slots from {pool.slots} to 3...")
                    pool.slots = 3
                    session.commit()
                else:
                    print(" 'scraper_pool' already exists with 3 slots.")
    except Exception as e:
        print(f" Could not initialize pool: {e}")

    # Auto-unpause DAGs
    try:
        from airflow.models import DagModel
        from airflow.utils.session import create_session

        target_dags = [
            'facebook_scraper_dag',
            'nextdoor_lead_scraper',
            'craigslist_lead_scraper',
            'facebook_owner_cookie_rotation',
            'nextdoor_owner_cookie_rotation',
            'ghl_onboarding_sync_dag'
        ]

        with create_session() as session:
            print(" Preparing to unpause DAGs for automatic execution...")
            for dag_id in target_dags:
                dag_model = session.query(DagModel).filter(DagModel.dag_id == dag_id).first()
                if dag_model:
                    if dag_model.is_paused:
                        dag_model.is_paused = False
                        print(f"▶ Unpaused DAG: {dag_id}")
                    else:
                        print(f" DAG '{dag_id}' is already active.")
                else:
                    print(f"ℹ DAG '{dag_id}' not found yet (will be active on first scan).")
            session.commit()
    except Exception as e:
        print(f" Could not unpause DAGs: {e}")

if __name__ == "__main__":
    initialize()
