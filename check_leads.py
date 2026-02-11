from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:47018")
client = MongoClient(mongo_uri)
db = client["PUFF"]

print("Latest Facebook Leads:")
for lead in db.Facebook_final_data.find().sort("_id", -1).limit(5):
    user = lead.get('extra_data', {}).get('user_detail', 'MISSING')
    print(f"Lead: {lead.get('title')[:30]} | User Detail: {user}")

print("\nLatest Nextdoor Leads:")
for lead in db.Nextdoor_final_data.find().sort("_id", -1).limit(5):
    user = lead.get('extra_data', {}).get('user_detail', 'MISSING')
    print(f"Lead: {lead.get('title')[:30]} | User Detail: {user}")
