import os
import json
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
import subprocess
import time

# Load environment variables
load_dotenv()

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "PUFF")
COLLECTION_NAME = "ghl_onboarding_test"

# Scraper Credentials from .env
FB_EMAIL = os.getenv("FACEBOOK_EMAIL")
FB_PASSWORD = os.getenv("FACEBOOK_PASSWORD")
ND_EMAIL = os.getenv("NEXTDOOR_EMAIL")
ND_PASSWORD = os.getenv("NEXTDOOR_PASSWORD")

def get_test_users():
    return [
        {
            "user": {
                "name": "Poonam",
                "email": "poonam.test@yopmail.com",
                "phone": "+919876543210"
            },
            "facebook": {
                "email": FB_EMAIL,
                "password": FB_PASSWORD,
                "target_keywords": "moving company, local movers, home relocation, packing services",
                "page_urls": "https://www.facebook.com/MovingCompany, https://www.facebook.com/LocalMoversUSA",
                "group_urls": "https://www.facebook.com/groups/movinghelp, https://www.facebook.com/groups/relocationservices"
            },
            "nextdoor": {
                "email": ND_EMAIL,
                "password": ND_PASSWORD,
                "target_keywords": "pest control, exterminator, termite treatment, bed bug removal",
                "page_urls": "https://nextdoor.com/pages/best-pest-control/, https://nextdoor.com/pages/neighborhood-exterminator/",
                "group_urls": "https://nextdoor.com/groups/local-services/, https://nextdoor.com/groups/home-maintenance/"
            },
            "craigslist": {
                "target_keywords": "roofing services, roof repair, gutter cleaning, skylight installation",
                "group_urls": "https://craigslist.org/d/roofing-contractor/search/rrs, https://craigslist.org/d/services/search/bbb"
            },
            "metadata": {
                "source": "GHL_Onboarding_Form",
                "environment": "test",
                "created_at": datetime.utcnow().isoformat()
            }
        },
        {
            "user": {
                "name": "John TestUser",
                "email": "john.test@yopmail.com",
                "phone": "+14155550101"
            },
            "facebook": {
                "email": FB_EMAIL,
                "password": FB_PASSWORD,
                "target_keywords": "plumbing services, emergency plumber, water heater repair, drain cleaning",
                "page_urls": "https://www.facebook.com/QualityPlumbing, https://www.facebook.com/EmergencyPlumbers",
                "group_urls": "https://www.facebook.com/groups/plumbingexperts, https://www.facebook.com/groups/homeownership"
            },
            "nextdoor": {
                "email": ND_EMAIL,
                "password": ND_PASSWORD,
                "target_keywords": "handyman services, home repairs, furniture assembly, painting",
                "page_urls": "https://nextdoor.com/pages/local-handyman/, https://nextdoor.com/pages/neighborhood-repairs/",
                "group_urls": "https://nextdoor.com/groups/diy-home-repair/, https://nextdoor.com/groups/neighbors-helping-neighbors/"
            },
            "craigslist": {
                "target_keywords": "house cleaning, maid services, deep cleaning, office cleaning",
                "group_urls": "https://craigslist.org/d/house-cleaning/search/hcc, https://craigslist.org/d/services/search/bbb"
            },
            "metadata": {
                "source": "GHL_Onboarding_Form",
                "environment": "test",
                "created_at": datetime.utcnow().isoformat()
            }
        },
        {
            "user": {
                "name": "Sarah TestUser",
                "email": "sarah.test@yopmail.com",
                "phone": "+14155550202"
            },
            "facebook": {
                "email": FB_EMAIL,
                "password": FB_PASSWORD,
                "target_keywords": "roofing leads, solar installation, energy efficient homes, roofing contractor",
                "page_urls": "https://www.facebook.com/SolarExperts, https://www.facebook.com/RoofingMasters",
                "group_urls": "https://www.facebook.com/groups/solarcommunity, https://www.facebook.com/groups/homeremodeling"
            },
            "nextdoor": {
                "email": ND_EMAIL,
                "password": ND_PASSWORD,
                "target_keywords": "landscaping, lawn care, garden maintenance, sprinkler repair",
                "page_urls": "https://nextdoor.com/pages/green-landscaping/, https://nextdoor.com/pages/garden-services/",
                "group_urls": "https://nextdoor.com/groups/gardening-tips/, https://nextdoor.com/groups/local-landscapers/"
            },
            "craigslist": {
                "target_keywords": "personal trainer, fitness coach, yoga instructor, wellness coach",
                "group_urls": "https://craigslist.org/d/lessons-tutoring/search/lss, https://craigslist.org/d/services/search/bbb"
            },
            "metadata": {
                "source": "GHL_Onboarding_Form",
                "environment": "test",
                "created_at": datetime.utcnow().isoformat()
            }
        },
        {
            "user": {
                "name": "Mike TestUser",
                "email": "mike.test@yopmail.com",
                "phone": "+14155550303"
            },
            "facebook": {
                "email": FB_EMAIL,
                "password": FB_PASSWORD,
                "target_keywords": "real estate leads, mortgage broker, home loans, first time home buyer",
                "page_urls": "https://www.facebook.com/RealEstatePros, https://www.facebook.com/MortgageGuide",
                "group_urls": "https://www.facebook.com/groups/realestateinvestors, https://www.facebook.com/groups/homebuyers"
            },
            "nextdoor": {
                "email": ND_EMAIL,
                "password": ND_PASSWORD,
                "target_keywords": "hvac repair, air conditioning service, furnace installation, heating repair",
                "page_urls": "https://nextdoor.com/pages/cool-hvac/, https://nextdoor.com/pages/comfort-heating/",
                "group_urls": "https://nextdoor.com/groups/home-appliances/, https://nextdoor.com/groups/neighborhood-services/"
            },
            "craigslist": {
                "target_keywords": "web development, website design, seo services, digital marketing",
                "group_urls": "https://craigslist.org/d/computer-services/search/cps, https://craigslist.org/d/services/search/bbb"
            },
            "metadata": {
                "source": "GHL_Onboarding_Form",
                "environment": "test",
                "created_at": datetime.utcnow().isoformat()
            }
        }
    ]

def seed_data():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[COLLECTION_NAME]
    
    users = get_test_users()
    
    # Clear existing test data
    collection.delete_many({"metadata.environment": "test"})
    
    # Insert new test data
    result = collection.insert_many(users)
    print(f"✓ Successfully seeded {len(result.inserted_ids)} users into {COLLECTION_NAME}")
    return users

def trigger_dags(users):
    print("\nTriggering DAGs for each user...")
    for user in users:
        user_email = user['user']['email']
        print(f"\n--- User: {user['user']['name']} ({user_email}) ---")
        
        # Facebook Config
        fb_urls = [u.strip() for u in (user['facebook']['page_urls'] + "," + user['facebook']['group_urls']).split(",") if u.strip()]
        fb_conf = {
            "urls": fb_urls,
            "keywords": user['facebook']['target_keywords'],
            "user_email": user_email
        }
        
        # Nextdoor Config
        nd_urls = [u.strip() for u in (user['nextdoor']['page_urls'] + "," + user['nextdoor']['group_urls']).split(",") if u.strip()]
        nd_conf = {
            "urls": nd_urls,
            "keywords": user['nextdoor']['target_keywords'],
            "user_email": user_email
        }
        
        # Craigslist Config
        cl_urls = [u.strip() for u in user['craigslist']['group_urls'].split(",") if u.strip()]
        cl_conf = {
            "urls": cl_urls,
            "keywords": user['craigslist']['target_keywords'],
            "user_email": user_email
        }
        
        # Command to trigger DAGs
        dags = [
            ("facebook_scraper_dag", fb_conf),
            ("nextdoor_lead_scraper", nd_conf),
            ("craigslist_lead_scraper", cl_conf)
        ]
        
        for dag_id, conf in dags:
            try:
                # 1. Try local airflow command
                cmd = ["airflow", "dags", "trigger", "-c", json.dumps(conf), dag_id]
                print(f"Attempting to trigger {dag_id} locally...")
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"✓ Triggered {dag_id} successfully")
            except (subprocess.CalledProcessError, FileNotFoundError):
                try:
                    # 2. Try via docker exec if local fails
                    print(f"Local airflow command failed. Attempting via Docker (airflow-scheduler)...")
                    cmd = [
                        "docker", "exec", "airflow-scheduler",
                        "airflow", "dags", "trigger",
                        "-c", json.dumps(conf),
                        dag_id
                    ]
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    print(f"✓ Triggered {dag_id} via Docker successfully")
                except Exception as e:
                    print(f"✗ Failed to trigger {dag_id}: {e}")
            except Exception as e:
                print(f"✗ Unexpected error triggering {dag_id}: {e}")

if __name__ == "__main__":
    test_users = seed_data()
    trigger_dags(test_users)
