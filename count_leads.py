from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:47018")
client = MongoClient(mongo_uri)
db = client["PUFF"]
for col in ['Nextdoor_final_data', 'Facebook_final_data', 'Craigslist_final_data']:
    print(f"{col} count: {db[col].count_documents({})}")
