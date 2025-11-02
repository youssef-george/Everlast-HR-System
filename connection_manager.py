"""
Connection management utilities for preventing database connection pool exhaustion
"""
import logging
from contextlib import contextmanager
from flask import current_app
from extensions import db
from functools import wraps
import threading

# Thread-local storage for tracking sync operations
_sync_lock = threading.Lock()
_active_syncs = set()

def is_sync_running():
    """Check if a sync operation is already running"""
    with _sync_lock:
        return len(_active_syncs) > 0

def register_sync_operation(operation_id):
    """Register a sync operation to prevent concurrent syncs"""
    with _sync_lock:
        _active_syncs.add(operation_id)
        logging.info(f"Registered sync operation: {operation_id}")

def unregister_sync_operation(operation_id):
    """Unregister a sync operation"""
    with _sync_lock:
        _active_syncs.discard(operation_id)
        logging.info(f"Unregistered sync operation: {operation_id}")

def clear_all_sync_operations():
    """Clear all sync operations (for debugging/reset purposes)"""
    with _sync_lock:
        cleared_count = len(_active_syncs)
        _active_syncs.clear()
        logging.info(f"Cleared {cleared_count} sync operations")
        return cleared_count

def get_connection_pool_status():
    """Get current connection pool status for monitoring"""
    try:
        from extensions import db
        pool = db.engine.pool
        return {
            'pool_size': pool.size(),
            'checked_in': pool.checkedin(),
            'checked_out': pool.checkedout(),
            'overflow': pool.overflow(),
            'invalid': pool.invalid(),
            'total_connections': pool.checkedout() + pool.checkedin(),
            'available_connections': pool.checkedin()
        }
    except Exception as e:
        logging.error(f"Error getting pool status: {str(e)}")
        return None

def emergency_connection_cleanup():
    """Emergency cleanup of database connections"""
    try:
        from extensions import db
        # Remove all sessions
        db.session.remove()
        
        # Get pool status before cleanup
        pool_status_before = get_connection_pool_status()
        
        # Force close all connections in pool
        db.engine.dispose()
        
        # Get pool status after cleanup
        pool_status_after = get_connection_pool_status()
        
        logging.warning("Emergency connection cleanup performed")
        logging.info(f"Pool before cleanup: {pool_status_before}")
        logging.info(f"Pool after cleanup: {pool_status_after}")
        
        return {
            'status': 'success',
            'before': pool_status_before,
            'after': pool_status_after
        }
    except Exception as e:
        logging.error(f"Error during emergency cleanup: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@contextmanager
def managed_db_session():
    """Context manager for database sessions with proper cleanup"""
    session = db.session
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Database session error: {str(e)}")
        raise
    finally:
        # Proper session cleanup for scoped sessions
        try:
            db.session.remove()  # This properly returns connection to pool
        except Exception as e:
            logging.warning(f"Error removing database session: {str(e)}")

def with_db_cleanup(func):
    """Decorator to ensure proper database cleanup after function execution"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            # Gentle cleanup - only close session, don't dispose engine
            try:
                db.session.remove()  # Use remove() instead of close() for scoped sessions
            except Exception as e:
                logging.warning(f"Error during database cleanup: {str(e)}")
    return wrapper

def safe_sync_operation(operation_id):
    """Decorator for sync operations to prevent concurrent execution and ensure cleanup"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check if sync is already running (with shorter timeout)
            if is_sync_running():
                logging.info(f"Sync operation {operation_id} skipped - another sync is already running")
                return {
                    'status': 'skipped',
                    'message': 'Another sync operation is already running'
                }
            
            # Register this sync operation
            register_sync_operation(operation_id)
            
            try:
                # Use managed database session
                with managed_db_session():
                    return func(*args, **kwargs)
            finally:
                # Always unregister the operation
                unregister_sync_operation(operation_id)
                
        return wrapper
    return decorator

