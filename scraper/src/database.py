"""
Database connection and operations management.
Provides centralized MongoDB connection handling with error recovery.
"""

from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

try:
    from .config import get_mongo_uri, get_mongo_db
except ImportError:
    from config import get_mongo_uri, get_mongo_db
try:
    from .logger import get_logger
except ImportError:
    from logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """
    Manages MongoDB connections and provides database operations.
    Implements connection pooling and automatic reconnection.
    """
    
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        """
        Initialize database manager.
        
        Args:
            uri: MongoDB connection URI (defaults to config value)
            db_name: Database name (defaults to config value)
        """
        self.uri = uri or get_mongo_uri()
        self.db_name = db_name or get_mongo_db()
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None
        
        logger.info("database_manager_initialized", db_name=self.db_name)
    
    @property
    def client(self) -> MongoClient:
        """
        Get MongoDB client, creating connection if needed.
        
        Returns:
            MongoClient: Active MongoDB client
        
        Raises:
            ConnectionFailure: If unable to connect to MongoDB
        """
        if self._client is None:
            self.connect()
        return self._client
    
    @property
    def db(self) -> Database:
        """
        Get database instance.
        
        Returns:
            Database: MongoDB database instance
        """
        if self._db is None:
            self._db = self.client[self.db_name]
        return self._db
    
    def connect(self) -> None:
        """
        Establish connection to MongoDB.
        
        Raises:
            ConnectionFailure: If unable to connect
        """
        try:
            logger.info("connecting_to_mongodb", uri=self._mask_uri(self.uri))
            
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
            )
            
            # Test connection
            self._client.admin.command('ping')
            
            self._db = self._client[self.db_name]
            
            logger.info("mongodb_connected", db_name=self.db_name)
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error("mongodb_connection_failed", error=str(e))
            raise
    
    def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("mongodb_disconnected")
    
    def get_collection(self, collection_name: str) -> Collection:
        """
        Get a collection from the database.
        
        Args:
            collection_name: Name of the collection
        
        Returns:
            Collection: MongoDB collection instance
        """
        return self.db[collection_name]
    
    def insert_one(self, collection_name: str, document: Dict[str, Any]) -> str:
        """
        Insert a single document into a collection.
        
        Args:
            collection_name: Name of the collection
            document: Document to insert
        
        Returns:
            str: Inserted document ID
        """
        try:
            collection = self.get_collection(collection_name)
            result = collection.insert_one(document)
            
            logger.debug(
                "document_inserted",
                collection=collection_name,
                document_id=str(result.inserted_id)
            )
            
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(
                "insert_failed",
                collection=collection_name,
                error=str(e)
            )
            raise
    
    def insert_many(self, collection_name: str, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Insert multiple documents into a collection.
        
        Args:
            collection_name: Name of the collection
            documents: List of documents to insert
        
        Returns:
            List[str]: List of inserted document IDs
        """
        if not documents:
            logger.warning("insert_many_called_with_empty_list", collection=collection_name)
            return []
        
        try:
            collection = self.get_collection(collection_name)
            result = collection.insert_many(documents, ordered=False)
            
            inserted_ids = [str(id) for id in result.inserted_ids]
            
            logger.info(
                "documents_inserted",
                collection=collection_name,
                count=len(inserted_ids)
            )
            
            return inserted_ids
            
        except Exception as e:
            logger.error(
                "insert_many_failed",
                collection=collection_name,
                document_count=len(documents),
                error=str(e)
            )
            raise
    
    def find_one(self, collection_name: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find a single document matching the query.
        
        Args:
            collection_name: Name of the collection
            query: Query filter
        
        Returns:
            Optional[Dict]: Found document or None
        """
        try:
            collection = self.get_collection(collection_name)
            document = collection.find_one(query)
            
            logger.debug(
                "find_one_executed",
                collection=collection_name,
                found=document is not None
            )
            
            return document
            
        except Exception as e:
            logger.error(
                "find_one_failed",
                collection=collection_name,
                error=str(e)
            )
            raise
    
    def find_many(
        self,
        collection_name: str,
        query: Dict[str, Any],
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find multiple documents matching the query.
        
        Args:
            collection_name: Name of the collection
            query: Query filter
            limit: Maximum number of documents to return
        
        Returns:
            List[Dict]: List of found documents
        """
        try:
            collection = self.get_collection(collection_name)
            cursor = collection.find(query)
            
            if limit:
                cursor = cursor.limit(limit)
            
            documents = list(cursor)
            
            logger.debug(
                "find_many_executed",
                collection=collection_name,
                count=len(documents)
            )
            
            return documents
            
        except Exception as e:
            logger.error(
                "find_many_failed",
                collection=collection_name,
                error=str(e)
            )
            raise
    
    def update_one(
        self,
        collection_name: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False
    ) -> int:
        """
        Update a single document.
        
        Args:
            collection_name: Name of the collection
            query: Query filter
            update: Update operations
            upsert: Whether to insert if not found
        
        Returns:
            int: Number of documents modified
        """
        try:
            collection = self.get_collection(collection_name)
            result = collection.update_one(query, update, upsert=upsert)
            
            logger.debug(
                "update_one_executed",
                collection=collection_name,
                modified=result.modified_count,
                upserted=result.upserted_id is not None
            )
            
            return result.modified_count
            
        except Exception as e:
            logger.error(
                "update_one_failed",
                collection=collection_name,
                error=str(e)
            )
            raise
    
    def delete_many(self, collection_name: str, query: Dict[str, Any]) -> int:
        """
        Delete documents matching the query.
        
        Args:
            collection_name: Name of the collection
            query: Query filter
        
        Returns:
            int: Number of documents deleted
        """
        try:
            collection = self.get_collection(collection_name)
            result = collection.delete_many(query)
            
            logger.info(
                "delete_many_executed",
                collection=collection_name,
                deleted=result.deleted_count
            )
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(
                "delete_many_failed",
                collection=collection_name,
                error=str(e)
            )
            raise
    
    @staticmethod
    def _mask_uri(uri: str) -> str:
        """
        Mask sensitive information in URI for logging.
        
        Args:
            uri: MongoDB connection URI
        
        Returns:
            str: Masked URI
        """
        if '@' in uri:
            # mongodb://user:password@host:port/db -> mongodb://***:***@host:port/db
            parts = uri.split('@')
            if '://' in parts[0]:
                protocol = parts[0].split('://')[0]
                return f"{protocol}://***:***@{parts[1]}"
        return uri
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    Get the global database manager instance.
    
    Returns:
        DatabaseManager: The database manager
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Automatically handles connection and disconnection.
    
    Yields:
        DatabaseManager: Connected database manager
    
    Example:
        with get_db_connection() as db:
            db.insert_one("leads", {"name": "John"})
    """
    db = DatabaseManager()
    try:
        db.connect()
        yield db
    finally:
        db.disconnect()


if __name__ == "__main__":
    # Test database connection
    try:
        with get_db_connection() as db:
            print("✓ Database connection successful")
            print(f"  Database: {db.db_name}")
            
            # Test insert
            test_id = db.insert_one("test_collection", {"test": "data"})
            print(f"  Test document inserted: {test_id}")
            
            # Clean up
            db.delete_many("test_collection", {"test": "data"})
            print("  Test document deleted")
            
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
