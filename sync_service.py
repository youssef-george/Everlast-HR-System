"""
Database Synchronization Service
Handles real-time sync between SQLite (primary) and PostgreSQL (secondary) databases.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from flask import current_app, g
from extensions import db
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseSyncService:
    """Handles synchronization between SQLite and PostgreSQL databases."""
    
    def __init__(self, app=None):
        self.app = app
        self.postgres_engine = None
        self.postgres_session_factory = None
        self.sync_enabled = True
        self.sync_lock = threading.Lock()
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the sync service with Flask app."""
        self.app = app
        
        # Create PostgreSQL engine
        postgres_uri = app.config.get('POSTGRES_DATABASE_URI')
        if postgres_uri:
            try:
                self.postgres_engine = create_engine(
                    postgres_uri,
                    **app.config.get('POSTGRES_ENGINE_OPTIONS', {})
                )
                
                # Create session factory
                self.postgres_session_factory = scoped_session(
                    sessionmaker(bind=self.postgres_engine)
                )
                
                # Test connection
                with self.postgres_engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                    logger.info("PostgreSQL connection established successfully")
                
                # Set up event listeners
                self.setup_event_listeners()
                
                self.sync_enabled = app.config.get('ENABLE_DB_SYNC', True)
                logger.info(f"Database sync service initialized. Sync enabled: {self.sync_enabled}")
                
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL connection: {str(e)}")
                self.sync_enabled = False
        else:
            logger.warning("No PostgreSQL URI configured. Sync disabled.")
            self.sync_enabled = False
    
    @contextmanager
    def get_postgres_session(self):
        """Get a PostgreSQL session with proper cleanup."""
        if not self.postgres_session_factory:
            raise RuntimeError("PostgreSQL session factory not initialized")
        
        session = self.postgres_session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"PostgreSQL session error: {str(e)}")
            raise
        finally:
            session.close()
    
    def setup_event_listeners(self):
        """Set up SQLAlchemy event listeners for automatic sync."""
        
        @event.listens_for(db.session, 'after_commit')
        def sync_after_commit(session):
            """Sync changes to PostgreSQL after SQLite commit."""
            if not self.sync_enabled:
                return
            
            try:
                # Get the changes from the session
                changes = self._extract_session_changes(session)
                if changes:
                    self._sync_changes_to_postgres(changes)
            except Exception as e:
                logger.error(f"Sync after commit failed: {str(e)}")
        
        @event.listens_for(db.session, 'after_rollback')
        def handle_rollback(session):
            """Handle rollback events."""
            logger.debug("SQLite session rolled back - no sync needed")
    
    def _extract_session_changes(self, session) -> Dict[str, List[Any]]:
        """Extract changes from SQLAlchemy session."""
        changes = {
            'new': [],
            'dirty': [],
            'deleted': []
        }
        
        # Note: After commit, the session is clean, so we need to track changes differently
        # This is a simplified approach - in production, you might want to use session events
        # to track changes before commit
        
        return changes
    
    def sync_record_to_postgres(self, operation: str, model_class, record_data: Dict[str, Any], record_id: Any = None):
        """
        Sync a single record to PostgreSQL.
        
        Args:
            operation: 'insert', 'update', or 'delete'
            model_class: SQLAlchemy model class
            record_data: Dictionary of record data
            record_id: Primary key value for update/delete operations
        """
        if not self.sync_enabled:
            return
        
        with self.sync_lock:
            try:
                with self.get_postgres_session() as pg_session:
                    table_name = model_class.__tablename__
                    
                    if operation == 'insert':
                        self._insert_record(pg_session, model_class, record_data)
                    elif operation == 'update':
                        self._update_record(pg_session, model_class, record_data, record_id)
                    elif operation == 'delete':
                        self._delete_record(pg_session, model_class, record_id)
                    
                    logger.debug(f"Synced {operation} for {table_name} record {record_id}")
                    
            except Exception as e:
                logger.error(f"Failed to sync {operation} for {model_class.__tablename__}: {str(e)}")
                self._handle_sync_error(operation, model_class, record_data, record_id, e)
    
    def _insert_record(self, pg_session, model_class, record_data: Dict[str, Any]):
        """Insert a record into PostgreSQL."""
        try:
            # Create new instance
            pg_record = model_class()
            
            # Set attributes
            for key, value in record_data.items():
                if hasattr(pg_record, key):
                    setattr(pg_record, key, value)
            
            # Use the postgres bind
            pg_session.bind = self.postgres_engine
            pg_session.add(pg_record)
            pg_session.flush()
            
        except IntegrityError as e:
            # Handle duplicate key errors - try update instead
            logger.warning(f"Insert failed due to integrity error, attempting update: {str(e)}")
            pg_session.rollback()
            
            # Try to find and update existing record
            primary_key = self._get_primary_key_value(model_class, record_data)
            if primary_key:
                self._update_record(pg_session, model_class, record_data, primary_key)
    
    def _update_record(self, pg_session, model_class, record_data: Dict[str, Any], record_id: Any):
        """Update a record in PostgreSQL."""
        # Bind session to postgres engine
        pg_session.bind = self.postgres_engine
        
        # Find existing record
        pg_record = pg_session.query(model_class).filter(
            getattr(model_class, self._get_primary_key_column(model_class)) == record_id
        ).first()
        
        if pg_record:
            # Update attributes
            for key, value in record_data.items():
                if hasattr(pg_record, key):
                    setattr(pg_record, key, value)
            pg_session.flush()
        else:
            # Record doesn't exist, insert it
            logger.warning(f"Record {record_id} not found for update, inserting instead")
            self._insert_record(pg_session, model_class, record_data)
    
    def _delete_record(self, pg_session, model_class, record_id: Any):
        """Delete a record from PostgreSQL."""
        # Bind session to postgres engine
        pg_session.bind = self.postgres_engine
        
        # Find and delete record
        pg_record = pg_session.query(model_class).filter(
            getattr(model_class, self._get_primary_key_column(model_class)) == record_id
        ).first()
        
        if pg_record:
            pg_session.delete(pg_record)
            pg_session.flush()
    
    def _get_primary_key_column(self, model_class) -> str:
        """Get the primary key column name for a model."""
        inspector = inspect(model_class)
        return inspector.primary_key[0].name
    
    def _get_primary_key_value(self, model_class, record_data: Dict[str, Any]) -> Any:
        """Extract primary key value from record data."""
        pk_column = self._get_primary_key_column(model_class)
        return record_data.get(pk_column)
    
    def _sync_changes_to_postgres(self, changes: Dict[str, List[Any]]):
        """Sync accumulated changes to PostgreSQL."""
        # This would be implemented based on how you track changes
        # For now, this is a placeholder
        pass
    
    def _handle_sync_error(self, operation: str, model_class, record_data: Dict[str, Any], record_id: Any, error: Exception):
        """Handle sync errors with retry logic."""
        retry_attempts = current_app.config.get('SYNC_RETRY_ATTEMPTS', 3)
        retry_delay = current_app.config.get('SYNC_RETRY_DELAY', 5)
        
        for attempt in range(retry_attempts):
            try:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                logger.info(f"Retrying sync operation {operation} for {model_class.__tablename__} (attempt {attempt + 1})")
                
                with self.get_postgres_session() as pg_session:
                    if operation == 'insert':
                        self._insert_record(pg_session, model_class, record_data)
                    elif operation == 'update':
                        self._update_record(pg_session, model_class, record_data, record_id)
                    elif operation == 'delete':
                        self._delete_record(pg_session, model_class, record_id)
                
                logger.info(f"Retry successful for {operation} on {model_class.__tablename__}")
                return
                
            except Exception as retry_error:
                logger.error(f"Retry attempt {attempt + 1} failed: {str(retry_error)}")
        
        # All retries failed
        logger.error(f"All retry attempts failed for {operation} on {model_class.__tablename__}. Manual intervention required.")
        self._log_failed_sync(operation, model_class, record_data, record_id, error)
    
    def _log_failed_sync(self, operation: str, model_class, record_data: Dict[str, Any], record_id: Any, error: Exception):
        """Log failed sync operations for manual recovery."""
        error_log = {
            'timestamp': time.time(),
            'operation': operation,
            'table': model_class.__tablename__,
            'record_id': record_id,
            'record_data': record_data,
            'error': str(error)
        }
        
        # Log to file or database for manual recovery
        logger.critical(f"SYNC FAILURE: {error_log}")
    
    def test_postgres_connection(self) -> bool:
        """Test PostgreSQL connection."""
        try:
            with self.postgres_engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            return True
        except Exception as e:
            logger.error(f"PostgreSQL connection test failed: {str(e)}")
            return False
    
    def disable_sync(self):
        """Temporarily disable sync."""
        self.sync_enabled = False
        logger.info("Database sync disabled")
    
    def enable_sync(self):
        """Re-enable sync."""
        self.sync_enabled = True
        logger.info("Database sync enabled")


# Global sync service instance
sync_service = DatabaseSyncService()


# Decorator for manual sync operations
def sync_to_postgres(operation: str):
    """
    Decorator to manually sync database operations to PostgreSQL.
    
    Usage:
        @sync_to_postgres('insert')
        def create_user(user_data):
            user = User(**user_data)
            db.session.add(user)
            db.session.commit()
            return user
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            # Extract model and data from result if needed
            # This is a simplified implementation
            if hasattr(result, '__tablename__'):
                record_data = {c.name: getattr(result, c.name) for c in result.__table__.columns}
                sync_service.sync_record_to_postgres(operation, result.__class__, record_data, result.id)
            
            return result
        return wrapper
    return decorator


# Context manager for batch sync operations
@contextmanager
def batch_sync_context():
    """Context manager for batch sync operations."""
    sync_service.disable_sync()
    try:
        yield
    finally:
        sync_service.enable_sync()


# Helper functions for manual sync
def sync_model_to_postgres(model_instance, operation='insert'):
    """Manually sync a model instance to PostgreSQL."""
    record_data = {c.name: getattr(model_instance, c.name) for c in model_instance.__table__.columns}
    primary_key = getattr(model_instance, sync_service._get_primary_key_column(model_instance.__class__))
    
    sync_service.sync_record_to_postgres(operation, model_instance.__class__, record_data, primary_key)


def bulk_sync_table_to_postgres(model_class, batch_size=100):
    """Sync all records from a table to PostgreSQL."""
    logger.info(f"Starting bulk sync for {model_class.__tablename__}")
    
    total_records = db.session.query(model_class).count()
    synced_records = 0
    
    for offset in range(0, total_records, batch_size):
        records = db.session.query(model_class).offset(offset).limit(batch_size).all()
        
        for record in records:
            try:
                sync_model_to_postgres(record, 'insert')
                synced_records += 1
            except Exception as e:
                logger.error(f"Failed to sync record {record.id}: {str(e)}")
        
        logger.info(f"Synced {synced_records}/{total_records} records for {model_class.__tablename__}")
    
    logger.info(f"Bulk sync completed for {model_class.__tablename__}: {synced_records}/{total_records} records")

