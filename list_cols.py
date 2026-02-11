from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:47018")
client = MongoClient(mongo_uri)
db = client["PUFF"]
print(f"Collections in PUFF: {db.list_collection_names()}")
