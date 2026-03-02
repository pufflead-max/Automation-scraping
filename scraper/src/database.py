"""Database connection and operations management  ."""

from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from pymongo import MongoClient, UpdateOne
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, BulkWriteError

try:
    from config import get_mongo_uri, get_mongo_db
    from logger import get_logger
except ImportError:
    from .config import get_mongo_uri, get_mongo_db
    from .logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    """Manages MongoDB connections and provides database operations."""
    
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri, self.db_name = uri or get_mongo_uri(), db_name or get_mongo_db()
        self._client, self._db = None, None
        logger.info("db_manager_init", db=self.db_name)
    
    @property
    def client(self) -> MongoClient:
        if self._client is None: self.connect()
        return self._client
    
    @property
    def db(self) -> Database:
        if self._db is None: self._db = self.client[self.db_name]
        return self._db
    
    def connect(self):
        try:
            masked = f"{self.uri.split('://')[0]}://***:***@{self.uri.split('@')[1]}" if '@' in self.uri else self.uri
            logger.info("connecting_to_mongodb", uri=masked)
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=10_000,   # 10s to pick a server
                connectTimeoutMS=10_000,           # 10s to open the TCP socket
                socketTimeoutMS=30_000,            # 30s max for any single query/response
            )
            self._client.admin.command('ping')
            self._db = self._client[self.db_name]
        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            raise
    
    def disconnect(self):
        if self._client is not None: self._client.close()
        self._client = self._db = None
    
    def ensure_collection(self, name: str):
        """Ensure a collection exists in the database."""
        if name not in self.db.list_collection_names():
            self.db.create_collection(name)
            logger.info("collection_created", name=name)

    def get_collection(self, name: str) -> Collection:
        # self.ensure_collection(name)
        return self.db[name]
    
    def insert_one(self, col: str, doc: Dict[str, Any]) -> str:
        res = self.get_collection(col).insert_one(doc)
        return str(res.inserted_id)
    
    def insert_many(self, col: str, docs: List[Dict[str, Any]]) -> List[str]:
        if not docs: return []
        res = self.get_collection(col).insert_many(docs, ordered=False)
        return [str(id) for id in res.inserted_ids]
    
    def find_one(self, col: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.get_collection(col).find_one(query)
    
    def find_many(self, col: str, query: Dict[str, Any], limit: int = 0) -> List[Dict[str, Any]]:
        cursor = self.get_collection(col).find(query)
        return list(cursor.limit(limit) if limit else cursor)
    
    def update_one(self, col: str, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> int:
        return self.get_collection(col).update_one(query, update, upsert=upsert).modified_count
    
    def delete_many(self, col: str, query: Dict[str, Any]) -> int:
        return self.get_collection(col).delete_many(query).deleted_count
    
    def bulk_upsert(self, col: str, docs: List[Dict[str, Any]], key: str) -> int:
        if not docs: return 0
        ops = [UpdateOne({key: d[key]}, {"$set": {k: v for k, v in d.items() if k != '_id'}}, upsert=True)
               for d in docs if key in d and d[key]]
        if not ops: return 0
        try:
            res = self.get_collection(col).bulk_write(ops, ordered=False)
            return res.modified_count + res.upserted_count
        except BulkWriteError as e:
            return e.details.get('nModified', 0) + e.details.get('nUpserted', 0)
    
    def find_leads_by_user(self, col: str, user_email: str, limit: int = 0) -> List[Dict[str, Any]]:
        """Find all leads for a specific user by email."""
        query = {"user_email": user_email}
        return self.find_many(col, query, limit)
    
    def count_leads_by_user(self, col: str, user_email: str) -> int:
        """Count leads for a specific user."""
        return self.get_collection(col).count_documents({"user_email": user_email})

_db_manager = None
def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None: _db_manager = DatabaseManager()
    return _db_manager

@contextmanager
def get_db_connection():
    db = DatabaseManager()
    try:
        db.connect()
        yield db
    finally: db.disconnect()
