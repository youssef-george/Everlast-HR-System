"""
Working Database Synchronization Service
Handles real-time sync between SQLite (primary) and PostgreSQL (secondary) databases.
Uses proper event tracking to capture changes before commit.
"""

import logging
import time
import threading
from typing import Any, Dict, List, Optional, Set
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from flask import current_app, g
from extensions import db

# Configure logging
logger = logging.getLogger(__name__)

class WorkingSyncService:
    """Handles synchronization between SQLite and PostgreSQL databases."""
    
    def __init__(self, app=None):
        self.app = app
        self.postgres_engine = None
        self.postgres_session_factory = None
        self.sync_enabled = True
        self.sync_lock = threading.Lock()
        
        # Thread-local storage for tracking changes
        self.local_data = threading.local()
        
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
                logger.info(f"Working sync service initialized. Sync enabled: {self.sync_enabled}")
                
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL connection: {str(e)}")
                self.sync_enabled = False
        else:
            logger.warning("No PostgreSQL URI configured. Sync disabled.")
            self.sync_enabled = False
    
    def setup_event_listeners(self):
        """Set up SQLAlchemy event listeners for automatic sync."""
        
        @event.listens_for(Session, 'before_flush')
        def capture_changes(session, flush_context, instances):
            """Capture changes before flush."""
            if not self.sync_enabled:
                return
            
            # Check if this is the primary SQLite session (not PostgreSQL)
            # Allow if bind is None (Flask-SQLAlchemy default) or if bind matches db.engine
            session_bind = getattr(session, 'bind', None)
            if session_bind is not None and session_bind != db.engine:
                return
            
            # Initialize thread-local storage
            if not hasattr(self.local_data, 'pending_changes'):
                self.local_data.pending_changes = {
                    'new': [],
                    'dirty': [],
                    'deleted': []
                }
            
            # Capture new instances
            for instance in session.new:
                if hasattr(instance, '__tablename__'):
                    serialized = self._serialize_instance(instance, 'insert')
                    if serialized:
                        self.local_data.pending_changes['new'].append(serialized)
                        logger.debug(f"Captured new {instance.__tablename__} record for sync")
            
            # Capture dirty instances
            for instance in session.dirty:
                if hasattr(instance, '__tablename__'):
                    serialized = self._serialize_instance(instance, 'update')
                    if serialized:
                        self.local_data.pending_changes['dirty'].append(serialized)
                        logger.debug(f"Captured updated {instance.__tablename__} record for sync")
            
            # Capture deleted instances
            for instance in session.deleted:
                if hasattr(instance, '__tablename__'):
                    serialized = self._serialize_instance(instance, 'delete')
                    if serialized:
                        self.local_data.pending_changes['deleted'].append(serialized)
                        logger.debug(f"Captured deleted {instance.__tablename__} record for sync")
        
        @event.listens_for(Session, 'after_commit')
        def sync_after_commit(session):
            """Sync changes to PostgreSQL after successful commit."""
            if not self.sync_enabled:
                return
            
            # Check if this is the primary SQLite session (not PostgreSQL)
            # After commit, bind might be None, so we allow None too
            session_bind = getattr(session, 'bind', None)
            if session_bind is not None and session_bind != db.engine:
                return
            
            try:
                if hasattr(self.local_data, 'pending_changes'):
                    changes = self.local_data.pending_changes
                    total_changes = len(changes.get('new', [])) + len(changes.get('dirty', [])) + len(changes.get('deleted', []))
                    
                    if total_changes > 0:
                        logger.info(f"Syncing {total_changes} changes to PostgreSQL: {len(changes.get('new', []))} inserts, {len(changes.get('dirty', []))} updates, {len(changes.get('deleted', []))} deletes")
                        self._sync_changes_to_postgres(changes)
                    else:
                        logger.debug("No pending changes to sync after commit")
                    
                    # Clear pending changes
                    self.local_data.pending_changes = {
                        'new': [],
                        'dirty': [],
                        'deleted': []
                    }
            except Exception as e:
                logger.error(f"Sync after commit failed: {str(e)}", exc_info=True)
        
        @event.listens_for(Session, 'after_rollback')
        def clear_changes_after_rollback(session):
            """Clear pending changes after rollback."""
            if hasattr(self.local_data, 'pending_changes'):
                self.local_data.pending_changes = {
                    'new': [],
                    'dirty': [],
                    'deleted': []
                }
            logger.debug("SQLite session rolled back - cleared pending changes")
    
    def _serialize_instance(self, instance, operation) -> Optional[Dict[str, Any]]:
        """Serialize a model instance to a dictionary."""
        try:
            data = {
                'operation': operation,
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
            return None
    
    def _sync_changes_to_postgres(self, changes: Dict[str, List[Dict[str, Any]]]):
        """Sync accumulated changes to PostgreSQL."""
        if not self.sync_enabled:
            return
        
        with self.sync_lock:
            try:
                with self.get_postgres_session() as pg_session:
                    # Track sync results
                    sync_results = {
                        'inserted': 0,
                        'updated': 0,
                        'deleted': 0,
                        'errors': []
                    }
                    
                    # Process deletions first (to avoid foreign key constraint issues)
                    for change in changes.get('deleted', []):
                        try:
                            self._process_change(pg_session, change)
                            sync_results['deleted'] += 1
                        except Exception as e:
                            error_msg = f"Delete failed for {change.get('table_name', 'unknown')}: {str(e)}"
                            logger.error(error_msg)
                            sync_results['errors'].append(error_msg)
                    
                    # Process updates
                    for change in changes.get('dirty', []):
                        try:
                            self._process_change(pg_session, change)
                            sync_results['updated'] += 1
                        except Exception as e:
                            error_msg = f"Update failed for {change.get('table_name', 'unknown')}: {str(e)}"
                            logger.error(error_msg)
                            sync_results['errors'].append(error_msg)
                    
                    # Process inserts last (to ensure foreign keys exist)
                    for change in changes.get('new', []):
                        try:
                            self._process_change(pg_session, change)
                            sync_results['inserted'] += 1
                        except Exception as e:
                            error_msg = f"Insert failed for {change.get('table_name', 'unknown')}: {str(e)}"
                            logger.error(error_msg)
                            sync_results['errors'].append(error_msg)
                    
                    # Commit all changes to PostgreSQL
                    pg_session.commit()
                    
                    total_changes = sync_results['inserted'] + sync_results['updated'] + sync_results['deleted']
                    if total_changes > 0:
                        logger.info(f"Successfully synced {total_changes} changes to PostgreSQL: "
                                   f"{sync_results['inserted']} inserts, {sync_results['updated']} updates, "
                                   f"{sync_results['deleted']} deletes")
                    
                    # Log any errors but don't fail the entire sync
                    if sync_results['errors']:
                        logger.warning(f"Sync completed with {len(sync_results['errors'])} errors: {sync_results['errors']}")
                    
            except Exception as e:
                logger.error(f"Failed to sync changes to PostgreSQL: {str(e)}", exc_info=True)
                self._handle_sync_error(changes, e)
                raise
    
    def _process_change(self, pg_session: Session, change: Dict[str, Any]):
        """Process a single change."""
        try:
            operation = change['operation']
            model_class = change['model_class']
            record_data = change['data']
            primary_key = change['primary_key']
            
            if operation == 'insert':
                self._insert_record(pg_session, model_class, record_data)
            elif operation == 'update':
                self._update_record(pg_session, model_class, record_data, primary_key)
            elif operation == 'delete':
                self._delete_record(pg_session, model_class, primary_key)
                
        except Exception as e:
            logger.error(f"Failed to process {operation} change: {str(e)}")
            raise
    
    def _insert_record(self, pg_session: Session, model_class, record_data: Dict[str, Any]):
        """Insert a record into PostgreSQL."""
        try:
            # Create new instance
            pg_record = model_class()
            
            # Set attributes
            for key, value in record_data.items():
                if hasattr(pg_record, key) and value is not None:
                    # Convert ISO format strings back to datetime if needed
                    if isinstance(value, str) and 'T' in value and ':' in value:
                        try:
                            from datetime import datetime
                            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        except:
                            pass  # Keep as string if conversion fails
                    
                    setattr(pg_record, key, value)
            
            pg_session.add(pg_record)
            pg_session.flush()  # Flush to get the ID if auto-increment
            logger.debug(f"Inserted {model_class.__tablename__} record into PostgreSQL")
            
        except IntegrityError as e:
            # Handle duplicate key errors - try update instead
            logger.warning(f"Insert failed due to integrity error (duplicate key), attempting update: {str(e)}")
            pg_session.rollback()
            
            # Try to find and update existing record
            primary_key = self._get_primary_key_value(model_class, record_data)
            if primary_key:
                self._update_record(pg_session, model_class, record_data, primary_key)
            else:
                raise ValueError(f"Cannot update record without primary key value")
        except Exception as e:
            logger.error(f"Failed to insert record into PostgreSQL: {str(e)}")
            raise
    
    def _update_record(self, pg_session: Session, model_class, record_data: Dict[str, Any], primary_key: Any):
        """Update a record in PostgreSQL."""
        try:
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
                updated_fields = []
                for key, value in record_data.items():
                    if hasattr(pg_record, key):
                        # Convert ISO format strings back to datetime if needed
                        if isinstance(value, str) and 'T' in value and ':' in value:
                            try:
                                from datetime import datetime
                                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            except:
                                pass
                        
                        # Only update if value has changed
                        current_value = getattr(pg_record, key, None)
                        if current_value != value:
                            setattr(pg_record, key, value)
                            updated_fields.append(key)
                
                if updated_fields:
                    pg_session.flush()
                    logger.debug(f"Updated {model_class.__tablename__} record (primary key: {primary_key}, fields: {updated_fields})")
                else:
                    logger.debug(f"No changes detected for {model_class.__tablename__} record (primary key: {primary_key})")
            else:
                # Record doesn't exist, insert it
                logger.warning(f"Record not found for update in PostgreSQL (primary key: {primary_key}), inserting instead")
                self._insert_record(pg_session, model_class, record_data)
        except Exception as e:
            logger.error(f"Failed to update record in PostgreSQL: {str(e)}")
            raise
    
    def _delete_record(self, pg_session: Session, model_class, primary_key: Any):
        """Delete a record from PostgreSQL."""
        try:
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
                logger.debug(f"Deleted {model_class.__tablename__} record with primary key: {primary_key}")
            else:
                logger.warning(f"Record not found for deletion in PostgreSQL: {primary_key} (may have been already deleted)")
        except Exception as e:
            logger.error(f"Error deleting record from PostgreSQL: {str(e)}")
            raise
    
    def _get_primary_key_column(self, model_class) -> str:
        """Get the primary key column name for a model."""
        inspector = inspect(model_class)
        return inspector.primary_key[0].name
    
    def _get_primary_key_value(self, model_class, record_data: Dict[str, Any]) -> Any:
        """Extract primary key value from record data."""
        pk_column = self._get_primary_key_column(model_class)
        return record_data.get(pk_column)
    
    def _handle_sync_error(self, changes: Dict[str, List[Dict[str, Any]]], error: Exception):
        """Handle sync errors with logging."""
        total_changes = len(changes['new']) + len(changes['dirty']) + len(changes['deleted'])
        logger.error(f"Failed to sync {total_changes} changes: {str(error)}")
        
        # Log details for manual recovery
        error_log = {
            'timestamp': time.time(),
            'changes': changes,
            'error': str(error)
        }
        logger.critical(f"SYNC FAILURE: {error_log}")
    
    @contextmanager
    def get_postgres_session(self):
        """Get a PostgreSQL session with proper cleanup."""
        if not self.postgres_session_factory:
            raise RuntimeError("PostgreSQL session factory not initialized")
        
        session = self.postgres_session_factory()
        try:
            yield session
            # Commit is now handled by _sync_changes_to_postgres
            # But we ensure it's committed here as a safety measure
            if session.is_active:
                session.commit()
                logger.debug("PostgreSQL session committed successfully")
        except Exception as e:
            if session.is_active:
                session.rollback()
            logger.error(f"PostgreSQL session error: {str(e)}", exc_info=True)
            raise
        finally:
            session.close()
    
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
            'pending_changes': getattr(self.local_data, 'pending_changes', {})
        }


# Global working sync service instance
working_sync_service = WorkingSyncService()


# Context manager for temporarily disabling sync
@contextmanager
def sync_disabled():
    """Context manager to temporarily disable sync."""
    original_state = working_sync_service.sync_enabled
    working_sync_service.disable_sync()
    try:
        yield
    finally:
        if original_state:
            working_sync_service.enable_sync()


# Manual sync function for immediate sync
def manual_sync_record(model_instance, operation='insert'):
    """Manually sync a model instance to PostgreSQL."""
    if not working_sync_service.sync_enabled:
        return
    
    try:
        serialized = working_sync_service._serialize_instance(model_instance, operation)
        if serialized:
            changes = {
                'new': [serialized] if operation == 'insert' else [],
                'dirty': [serialized] if operation == 'update' else [],
                'deleted': [serialized] if operation == 'delete' else []
            }
            working_sync_service._sync_changes_to_postgres(changes)
    except Exception as e:
        logger.error(f"Manual sync failed: {str(e)}")


if __name__ == "__main__":
    print("Working sync service module loaded successfully")
    print("Features:")
    print("- Proper event tracking with before_flush and after_commit")
    print("- Thread-local storage for change tracking")
    print("- Automatic serialization of model instances")
    print("- Manual sync functions")
    print("- Comprehensive error handling")

