import os
from pymongo import MongoClient

def main():
    mongo_uri = "mongodb://scraper_admin:Mongodb_password12345@mongo:27017/PUFF?authSource=PUFF" # "mongodb://scraper_admin:Mongodb_password12345@localhost:47018/PUFF?authSource=PUFF"
    job_name = os.environ.get("JOB_NAME", "example")

    client = MongoClient(mongo_uri)
    db = client["PUFF"]

    db.runs.insert_one({"job": job_name, "status": "started"})
    # TODO: your scraping logic here
    db.runs.insert_one({"job": job_name, "status": "finished"})

if __name__ == "__main__":
    main()
