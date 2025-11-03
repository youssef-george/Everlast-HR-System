#!/usr/bin/env python3
"""
Migrate Everlast ERP from SQLite to PostgreSQL as Primary Database
This is a one-time migration script to move all data from SQLite to PostgreSQL.
"""
import os
import sys
import logging
from datetime import datetime
from sqlalchemy import create_engine, text, inspect, MetaData, Table
from sqlalchemy.orm import sessionmaker
# Using raw SQL instead of pandas for better reliability

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def migrate_to_postgres_primary():
    """Migrate all data from SQLite to PostgreSQL."""
    from config import Config
    
    logger.info("=" * 70)
    logger.info("EVERLAST ERP - SQLite to PostgreSQL Migration")
    logger.info("=" * 70)
    
    # Database connections
    sqlite_uri = Config.SQLITE_BACKUP_URI
    postgres_uri = Config.DATABASE_URL
    
    logger.info(f"SQLite Source: {sqlite_uri}")
    logger.info(f"PostgreSQL Target: {postgres_uri}")
    
    # Create engines
    try:
        sqlite_engine = create_engine(sqlite_uri)
        postgres_engine = create_engine(postgres_uri, pool_pre_ping=True)
        
        # Test connections
        logger.info("\n[1] Testing database connections...")
        with sqlite_engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        logger.info("[OK] SQLite connection successful")
        
        with postgres_engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        logger.info("[OK] PostgreSQL connection successful")
        
    except Exception as e:
        logger.error(f"[ERROR] Connection failed: {str(e)}")
        return False
    
    # Get table list
    logger.info("\n[2] Discovering tables...")
    sqlite_inspector = inspect(sqlite_engine)
    sqlite_tables = sqlite_inspector.get_table_names()
    
    logger.info(f"Found {len(sqlite_tables)} tables in SQLite:")
    for table in sqlite_tables:
        with sqlite_engine.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            logger.info(f"  - {table}: {count} records")
    
    # Create PostgreSQL schema from models
    logger.info("\n[3] Creating PostgreSQL schema...")
    try:
        from app import create_app
        from extensions import db
        
        app = create_app()
        with app.app_context():
            # Create all tables in PostgreSQL
            db.metadata.create_all(bind=postgres_engine)
            logger.info("[OK] PostgreSQL schema created")
            
    except Exception as e:
        logger.warning(f"[WARNING] Schema creation: {str(e)}")
        logger.info("Continuing with migration...")
    
    # Migration order (respecting foreign key dependencies)
    migration_order = [
        'departments',
        'users',
        'device_settings',
        'leave_types',
        'paid_holidays',
        'device_users',
        'attendance_logs',
        'daily_attendance',
        'leave_requests',
        'permission_requests',
        'fingerprint_failures',
        'leave_balances',
        'smtp_configurations',
        'employee_attachments',
        'alembic_version'
    ]
    
    # Add any remaining tables
    for table in sqlite_tables:
        if table not in migration_order:
            migration_order.append(table)
    
    # Migrate data
    logger.info("\n[4] Migrating data...")
    total_migrated = 0
    total_errors = 0
    
    for table_name in migration_order:
        if table_name not in sqlite_tables:
            logger.info(f"[SKIP] Table {table_name} not found in SQLite")
            continue
        
        try:
            # Get record counts
            with sqlite_engine.connect() as conn:
                sqlite_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            
            with postgres_engine.connect() as conn:
                try:
                    pg_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                except:
                    pg_count = 0
            
            if sqlite_count == 0:
                logger.info(f"[SKIP] {table_name}: Empty table")
                continue
            
            if pg_count >= sqlite_count:
                logger.info(f"[SKIP] {table_name}: Already migrated ({pg_count} >= {sqlite_count})")
                continue
            
            missing = sqlite_count - pg_count
            logger.info(f"\n[{table_name}] Migrating {missing} records...")
            
            # Use raw SQL for efficient migration
            batch_size = 1000
            migrated = 0
            
            # Get table structure
            sqlite_metadata = MetaData()
            sqlite_table = Table(table_name, sqlite_metadata, autoload_with=sqlite_engine)
            
            postgres_metadata = MetaData()
            try:
                postgres_table = Table(table_name, postgres_metadata, autoload_with=postgres_engine)
            except:
                logger.error(f"  [ERROR] Table {table_name} doesn't exist in PostgreSQL")
                total_errors += missing
                continue
            
            # Get column names
            columns = [col.name for col in sqlite_table.columns]
            col_names = ', '.join(columns)
            placeholders = ', '.join([f':{col}' for col in columns])
            
            # Get max ID in PostgreSQL
            with postgres_engine.connect() as conn:
                try:
                    result = conn.execute(text(f"SELECT MAX(id) FROM {table_name}"))
                    max_id = result.scalar() or 0
                except:
                    max_id = 0
            
            for offset in range(0, missing, batch_size):
                try:
                    # Read from SQLite
                    with sqlite_engine.connect() as sqlite_conn:
                        query = text(f"SELECT * FROM {table_name} WHERE id > :max_id ORDER BY id LIMIT :limit OFFSET :offset")
                        rows = sqlite_conn.execute(query, {"max_id": max_id, "limit": batch_size, "offset": offset}).fetchall()
                    
                    if not rows:
                        break
                    
                    # Build INSERT statement (ON CONFLICT only for tables with unique constraints)
                    # Check if table has id column (primary key)
                    has_id = 'id' in columns
                    if has_id:
                        insert_sql = f"""
                            INSERT INTO {table_name} ({col_names})
                            VALUES ({placeholders})
                            ON CONFLICT (id) DO NOTHING
                        """
                    else:
                        insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
                    
                    # Convert rows to dicts and insert
                    with postgres_engine.connect() as pg_conn:
                        trans = pg_conn.begin()
                        try:
                            for row in rows:
                                row_dict = dict(row._mapping) if hasattr(row, '_mapping') else {col: row[i] for i, col in enumerate(columns)}
                                
                                # Handle boolean conversion for is_extra_scan
                                if 'is_extra_scan' in row_dict and isinstance(row_dict['is_extra_scan'], (int, float)):
                                    row_dict['is_extra_scan'] = bool(row_dict['is_extra_scan'])
                                
                                pg_conn.execute(text(insert_sql), row_dict)
                                migrated += 1
                            
                            trans.commit()
                            logger.info(f"  Progress: {migrated}/{missing} records...")
                        except Exception as e:
                            trans.rollback()
                            # Try without ON CONFLICT for tables without unique constraint
                            try:
                                simple_insert = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
                                trans2 = pg_conn.begin()
                                for row in rows:
                                    row_dict = dict(row._mapping) if hasattr(row, '_mapping') else {col: row[i] for i, col in enumerate(columns)}
                                    if 'is_extra_scan' in row_dict and isinstance(row_dict['is_extra_scan'], (int, float)):
                                        row_dict['is_extra_scan'] = bool(row_dict['is_extra_scan'])
                                    pg_conn.execute(text(simple_insert), row_dict)
                                    migrated += 1
                                trans2.commit()
                                logger.info(f"  Progress: {migrated}/{missing} records...")
                            except Exception as e2:
                                trans2.rollback()
                                logger.error(f"  [ERROR] Batch migration failed: {str(e2)}")
                                total_errors += len(rows)
                    
                except Exception as e:
                    logger.error(f"  [ERROR] Batch migration failed: {str(e)}")
                    total_errors += min(batch_size, missing - migrated)
            
            logger.info(f"[OK] {table_name}: {migrated} records migrated")
            total_migrated += migrated
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to migrate {table_name}: {str(e)}")
            total_errors += sqlite_count
    
    # Verify migration
    logger.info("\n[5] Verifying migration...")
    verification_passed = True
    
    for table_name in migration_order:
        if table_name not in sqlite_tables:
            continue
        
        try:
            with sqlite_engine.connect() as conn:
                sqlite_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            
            with postgres_engine.connect() as conn:
                pg_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            
            if sqlite_count != pg_count:
                logger.warning(f"[WARNING] {table_name}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
                verification_passed = False
            else:
                logger.info(f"[OK] {table_name}: {pg_count} records (matches SQLite)")
                
        except Exception as e:
            logger.error(f"[ERROR] Verification failed for {table_name}: {str(e)}")
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total records migrated: {total_migrated}")
    logger.info(f"Errors encountered: {total_errors}")
    logger.info(f"Verification: {'PASSED' if verification_passed else 'FAILED'}")
    
    if verification_passed:
        logger.info("\n[SUCCESS] Migration completed successfully!")
        logger.info("PostgreSQL is now ready to use as primary database.")
    else:
        logger.warning("\n[WARNING] Migration completed with some discrepancies.")
        logger.warning("Please review the logs and verify data manually.")
    
    logger.info("=" * 70)
    
    return verification_passed

if __name__ == '__main__':
    success = migrate_to_postgres_primary()
    sys.exit(0 if success else 1)

