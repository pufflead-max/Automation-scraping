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
    
    for key, value in vars_to_set.items():
        try:
            # Check if variable already exists
            existing_val = Variable.get(key)
            print(f"✓ Variable '{key}' already exists. Skipping initialization.")
        except Exception:
            # If it doesn't exist, create it
            Variable.set(key, value)
            print(f"+ Initialized Variable '{key}' with default value.")

if __name__ == "__main__":
    initialize()
