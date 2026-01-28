"""Database connection and operations management."""

from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from pymongo import MongoClient, UpdateOne
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, BulkWriteError

try:
    from .config import get_mongo_uri, get_mongo_db
    from .logger import get_logger
except ImportError:
    from config import get_mongo_uri, get_mongo_db
    from logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Manages MongoDB connections and provides database operations."""
    
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri = uri or get_mongo_uri()
        self.db_name = db_name or get_mongo_db()
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None
        logger.info("database_manager_initialized", db_name=self.db_name)
    
    @property
    def client(self) -> MongoClient:
        if self._client is None:
            self.connect()
        return self._client
    
    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = self.client[self.db_name]
        return self._db
    
    def connect(self) -> None:
        try:
            logger.info("connecting_to_mongodb", uri=self._mask_uri(self.uri))
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=10000)
            self._client.admin.command('ping')
            self._db = self._client[self.db_name]
            logger.info("mongodb_connected", db_name=self.db_name)
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error("mongodb_connection_failed", error=str(e))
            raise
    
    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("mongodb_disconnected")
    
    def get_collection(self, collection_name: str) -> Collection:
        return self.db[collection_name]
    
    def insert_one(self, collection_name: str, document: Dict[str, Any]) -> str:
        try:
            result = self.get_collection(collection_name).insert_one(document)
            logger.debug("document_inserted", collection=collection_name, document_id=str(result.inserted_id))
            return str(result.inserted_id)
        except Exception as e:
            logger.error("insert_failed", collection=collection_name, error=str(e))
            raise
    
    def insert_many(self, collection_name: str, documents: List[Dict[str, Any]]) -> List[str]:
        if not documents:
            logger.warning("insert_many_called_with_empty_list", collection=collection_name)
            return []
        
        try:
            result = self.get_collection(collection_name).insert_many(documents, ordered=False)
            inserted_ids = [str(id) for id in result.inserted_ids]
            logger.info("documents_inserted", collection=collection_name, count=len(inserted_ids))
            return inserted_ids
        except Exception as e:
            logger.error("insert_many_failed", collection=collection_name, document_count=len(documents), error=str(e))
            raise
    
    def find_one(self, collection_name: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            document = self.get_collection(collection_name).find_one(query)
            logger.debug("find_one_executed", collection=collection_name, found=document is not None)
            return document
        except Exception as e:
            logger.error("find_one_failed", collection=collection_name, error=str(e))
            raise
    
    def find_many(self, collection_name: str, query: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            cursor = self.get_collection(collection_name).find(query)
            if limit:
                cursor = cursor.limit(limit)
            documents = list(cursor)
            logger.debug("find_many_executed", collection=collection_name, count=len(documents))
            return documents
        except Exception as e:
            logger.error("find_many_failed", collection=collection_name, error=str(e))
            raise
    
    def update_one(self, collection_name: str, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> int:
        try:
            result = self.get_collection(collection_name).update_one(query, update, upsert=upsert)
            logger.debug("update_one_executed", collection=collection_name, modified=result.modified_count, upserted=result.upserted_id is not None)
            return result.modified_count
        except Exception as e:
            logger.error("update_one_failed", collection=collection_name, error=str(e))
            raise
    
    def delete_many(self, collection_name: str, query: Dict[str, Any]) -> int:
        try:
            result = self.get_collection(collection_name).delete_many(query)
            logger.info("delete_many_executed", collection=collection_name, deleted=result.deleted_count)
            return result.deleted_count
        except Exception as e:
            logger.error("delete_many_failed", collection=collection_name, error=str(e))
            raise
    
    def bulk_upsert(self, collection_name: str, documents: List[Dict[str, Any]], unique_field: str) -> int:
        if not documents:
            return 0
        
        try:
            operations = [UpdateOne({unique_field: doc[unique_field]}, {"$set": {k: v for k, v in doc.items() if k != '_id'}}, upsert=True)
                         for doc in documents if unique_field in doc and doc[unique_field]]
            
            if not operations:
                logger.warning("bulk_upsert_no_valid_operations", collection=collection_name)
                return 0
            
            result = self.get_collection(collection_name).bulk_write(operations, ordered=False)
            count = result.modified_count + result.upserted_count
            logger.info("documents_upserted", collection=collection_name, count=count, modified=result.modified_count, upserted=result.upserted_count)
            return count
        except BulkWriteError as bwe:
            logger.error("bulk_upsert_partial_failure", collection=collection_name, error=str(bwe.details))
            return bwe.details.get('nModified', 0) + bwe.details.get('nUpserted', 0)
        except Exception as e:
            logger.error("bulk_upsert_failed", collection=collection_name, error=str(e))
            raise
    
    @staticmethod
    def _mask_uri(uri: str) -> str:
        if '@' in uri and '://' in (parts := uri.split('@'))[0]:
            return f"{parts[0].split('://')[0]}://***:***@{parts[1]}"
        return uri
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


@contextmanager
def get_db_connection():
    db = DatabaseManager()
    try:
        db.connect()
        yield db
    finally:
        db.disconnect()
