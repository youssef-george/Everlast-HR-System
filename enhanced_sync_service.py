"""
Enhanced Database Synchronization Service
Provides advanced real-time sync between SQLite and PostgreSQL with event listeners.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from flask import current_app, g
from extensions import db

logger = logging.getLogger(__name__)


class EnhancedSyncService:
    """Enhanced synchronization service with proper event tracking."""
    
    def __init__(self, app=None):
        self.app = app
        self.postgres_engine = None
        self.postgres_session_factory = None
        self.sync_enabled = True
        self.sync_lock = threading.Lock()
        
        # Track changes during session lifecycle
        self.pending_changes = threading.local()
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the enhanced sync service with Flask app."""
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
                
                # Set up enhanced event listeners
                self.setup_enhanced_event_listeners()
                
                self.sync_enabled = app.config.get('ENABLE_DB_SYNC', True)
                logger.info(f"Enhanced database sync service initialized. Sync enabled: {self.sync_enabled}")
                
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL connection: {str(e)}")
                self.sync_enabled = False
        else:
            logger.warning("No PostgreSQL URI configured. Sync disabled.")
            self.sync_enabled = False
    
    def setup_enhanced_event_listeners(self):
        """Set up comprehensive SQLAlchemy event listeners."""
        
        @event.listens_for(Session, 'before_flush')
        def track_changes_before_flush(session, flush_context, instances):
            """Track changes before they are flushed to the database."""
            if not self.sync_enabled:
                return
            
            # Initialize pending changes for this thread
            if not hasattr(self.pending_changes, 'changes'):
                self.pending_changes.changes = {
                    'new': [],
                    'dirty': [],
                    'deleted': []
                }
            
            # Track new instances
            for instance in session.new:
                if hasattr(instance, '__tablename__'):
                    self.pending_changes.changes['new'].append(self._serialize_instance(instance))
            
            # Track dirty instances
            for instance in session.dirty:
                if hasattr(instance, '__tablename__'):
                    self.pending_changes.changes['dirty'].append(self._serialize_instance(instance))
            
            # Track deleted instances
            for instance in session.deleted:
                if hasattr(instance, '__tablename__'):
                    self.pending_changes.changes['deleted'].append(self._serialize_instance(instance))
        
        @event.listens_for(Session, 'after_commit')
        def sync_after_commit(session):
            """Sync changes to PostgreSQL after successful commit."""
            if not self.sync_enabled:
                return
            
            try:
                if hasattr(self.pending_changes, 'changes'):
                    changes = self.pending_changes.changes
                    if any(changes.values()):  # If there are any changes
                        self._sync_changes_to_postgres(changes)
                    
                    # Clear pending changes
                    self.pending_changes.changes = {
                        'new': [],
                        'dirty': [],
                        'deleted': []
                    }
            except Exception as e:
                logger.error(f"Sync after commit failed: {str(e)}")
        
        @event.listens_for(Session, 'after_rollback')
        def clear_changes_after_rollback(session):
            """Clear pending changes after rollback."""
            if hasattr(self.pending_changes, 'changes'):
                self.pending_changes.changes = {
                    'new': [],
                    'dirty': [],
                    'deleted': []
                }
            logger.debug("SQLite session rolled back - cleared pending changes")
    
    def _serialize_instance(self, instance) -> Dict[str, Any]:
        """Serialize a model instance to a dictionary."""
        try:
            data = {
                'table_name': instance.__tablename__,
                'model_class': instance.__class__,
                'data': {}
            }
            
            # Get primary key
            primary_key_cols = [col.name for col in instance.__table__.primary_key.columns]
            
            # Serialize all columns
            for column in instance.__table__.columns:
                value = getattr(instance, column.name, None)
                # Handle datetime and other special types
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                data['data'][column.name] = value
            
            # Store primary key separately for easier access
            if len(primary_key_cols) == 1:
                data['primary_key'] = getattr(instance, primary_key_cols[0], None)
            else:
                data['primary_key'] = {col: getattr(instance, col, None) for col in primary_key_cols}
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to serialize instance: {str(e)}")
            return {}
    
    def _sync_changes_to_postgres(self, changes: Dict[str, List[Dict[str, Any]]]):
        """Sync accumulated changes to PostgreSQL."""
        if not self.sync_enabled:
            return
        
        with self.sync_lock:
            try:
                with self.get_postgres_session() as pg_session:
                    # Process deletions first
                    for change in changes['deleted']:
                        self._process_delete_change(pg_session, change)
                    
                    # Process updates
                    for change in changes['dirty']:
                        self._process_update_change(pg_session, change)
                    
                    # Process inserts last
                    for change in changes['new']:
                        self._process_insert_change(pg_session, change)
                    
                    logger.debug(f"Synced changes: {len(changes['new'])} inserts, "
                               f"{len(changes['dirty'])} updates, {len(changes['deleted'])} deletes")
                    
            except Exception as e:
                logger.error(f"Failed to sync changes to PostgreSQL: {str(e)}")
    
    def _process_insert_change(self, pg_session: Session, change: Dict[str, Any]):
        """Process an insert change."""
        try:
            model_class = change['model_class']
            record_data = change['data']
            
            # Create new instance
            pg_record = model_class()
            
            # Set attributes
            for key, value in record_data.items():
                if hasattr(pg_record, key):
                    # Convert ISO format strings back to datetime if needed
                    if isinstance(value, str) and 'T' in value and ':' in value:
                        try:
                            from datetime import datetime
                            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        except:
                            pass  # Keep as string if conversion fails
                    
                    setattr(pg_record, key, value)
            
            pg_session.add(pg_record)
            pg_session.flush()
            
        except IntegrityError as e:
            # Handle duplicate key errors
            logger.warning(f"Insert failed due to integrity error, attempting update: {str(e)}")
            pg_session.rollback()
            self._process_update_change(pg_session, change)
        except Exception as e:
            logger.error(f"Failed to process insert change: {str(e)}")
            pg_session.rollback()
    
    def _process_update_change(self, pg_session: Session, change: Dict[str, Any]):
        """Process an update change."""
        try:
            model_class = change['model_class']
            record_data = change['data']
            primary_key = change['primary_key']
            
            # Find existing record
            if isinstance(primary_key, dict):
                # Composite primary key
                filters = {col: val for col, val in primary_key.items()}
                pg_record = pg_session.query(model_class).filter_by(**filters).first()
            else:
                # Single primary key
                pk_column = self._get_primary_key_column(model_class)
                pg_record = pg_session.query(model_class).filter(
                    getattr(model_class, pk_column) == primary_key
                ).first()
            
            if pg_record:
                # Update attributes
                for key, value in record_data.items():
                    if hasattr(pg_record, key):
                        # Convert ISO format strings back to datetime if needed
                        if isinstance(value, str) and 'T' in value and ':' in value:
                            try:
                                from datetime import datetime
                                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            except:
                                pass
                        
                        setattr(pg_record, key, value)
                
                pg_session.flush()
            else:
                # Record doesn't exist, insert it
                logger.warning(f"Record not found for update, inserting instead")
                self._process_insert_change(pg_session, change)
                
        except Exception as e:
            logger.error(f"Failed to process update change: {str(e)}")
            pg_session.rollback()
    
    def _process_delete_change(self, pg_session: Session, change: Dict[str, Any]):
        """Process a delete change."""
        try:
            model_class = change['model_class']
            primary_key = change['primary_key']
            
            # Find and delete record
            if isinstance(primary_key, dict):
                # Composite primary key
                filters = {col: val for col, val in primary_key.items()}
                pg_record = pg_session.query(model_class).filter_by(**filters).first()
            else:
                # Single primary key
                pk_column = self._get_primary_key_column(model_class)
                pg_record = pg_session.query(model_class).filter(
                    getattr(model_class, pk_column) == primary_key
                ).first()
            
            if pg_record:
                pg_session.delete(pg_record)
                pg_session.flush()
            else:
                logger.warning(f"Record not found for deletion: {primary_key}")
                
        except Exception as e:
            logger.error(f"Failed to process delete change: {str(e)}")
            pg_session.rollback()
    
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
    
    def _get_primary_key_column(self, model_class) -> str:
        """Get the primary key column name for a model."""
        inspector = inspect(model_class)
        return inspector.primary_key[0].name
    
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
    
    def get_sync_stats(self) -> Dict[str, Any]:
        """Get synchronization statistics."""
        return {
            'sync_enabled': self.sync_enabled,
            'postgres_connected': self.test_postgres_connection() if self.postgres_engine else False,
            'postgres_engine_available': self.postgres_engine is not None,
            'pending_changes': getattr(self.pending_changes, 'changes', {})
        }


# Global enhanced sync service instance
enhanced_sync_service = EnhancedSyncService()


# Context manager for temporarily disabling sync
@contextmanager
def sync_disabled():
    """Context manager to temporarily disable sync."""
    original_state = enhanced_sync_service.sync_enabled
    enhanced_sync_service.disable_sync()
    try:
        yield
    finally:
        if original_state:
            enhanced_sync_service.enable_sync()


# Decorator to disable sync for specific functions
def without_sync(func):
    """Decorator to disable sync for a specific function."""
    def wrapper(*args, **kwargs):
        with sync_disabled():
            return func(*args, **kwargs)
    return wrapper


if __name__ == "__main__":
    print("Enhanced sync service module loaded successfully")
    print("Features:")
    print("- Real-time change tracking with SQLAlchemy events")
    print("- Automatic serialization of model instances")
    print("- Proper handling of datetime fields")
    print("- Composite primary key support")
    print("- Context managers for batch operations")
    print("- Comprehensive error handling and logging")

