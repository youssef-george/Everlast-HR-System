#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script
Migrates all data and schema from SQLite to PostgreSQL database.
"""

import os
import sys
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy import create_engine, MetaData, Table, text, inspect
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.schema import CreateTable
from flask import Flask

# Add the current directory to Python path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from models import *  # Import all models
from extensions import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SQLiteToPostgresMigrator:
    """Handles migration from SQLite to PostgreSQL."""
    
    def __init__(self, sqlite_uri: str, postgres_uri: str):
        self.sqlite_uri = sqlite_uri
        self.postgres_uri = postgres_uri
        
        # Create engines
        self.sqlite_engine = create_engine(sqlite_uri)
        self.postgres_engine = create_engine(postgres_uri)
        
        # Create session factories
        self.sqlite_session = scoped_session(sessionmaker(bind=self.sqlite_engine))
        self.postgres_session = scoped_session(sessionmaker(bind=self.postgres_engine))
        
        # Migration statistics
        self.stats = {
            'tables_migrated': 0,
            'records_migrated': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }
    
    def test_connections(self) -> bool:
        """Test both database connections."""
        try:
            # Test SQLite connection
            with self.sqlite_engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            logger.info("✓ SQLite connection successful")
            
            # Test PostgreSQL connection
            with self.postgres_engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            logger.info("✓ PostgreSQL connection successful")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Connection test failed: {str(e)}")
            return False
    
    def get_table_dependencies(self) -> List[str]:
        """
        Get tables in dependency order (tables with no foreign keys first).
        This ensures we migrate data in the correct order.
        """
        # Define the migration order based on foreign key dependencies
        # Tables with no dependencies first, then tables that depend on them
        migration_order = [
            'departments',
            'users',
            'leave_types',
            'paid_holidays',
            'attendance_data',
            'leave_requests',
            'permission_requests',
            'fingerprint_failures',
            'leave_balances',
            'user_activities'
        ]
        
        # Get all table names from SQLite
        inspector = inspect(self.sqlite_engine)
        existing_tables = inspector.get_table_names()
        
        # Filter to only include tables that exist and are in our models
        ordered_tables = []
        for table in migration_order:
            if table in existing_tables:
                ordered_tables.append(table)
        
        # Add any remaining tables not in our predefined order
        for table in existing_tables:
            if table not in ordered_tables:
                ordered_tables.append(table)
        
        logger.info(f"Migration order: {ordered_tables}")
        return ordered_tables
    
    def create_postgres_schema(self) -> bool:
        """Create PostgreSQL schema from SQLAlchemy models."""
        try:
            logger.info("Creating PostgreSQL schema...")
            
            # Create Flask app context to access models
            app = Flask(__name__)
            app.config.from_object(Config)
            
            with app.app_context():
                db.init_app(app)
                
                # Create all tables in PostgreSQL
                with self.postgres_engine.connect() as conn:
                    db.metadata.create_all(bind=conn)
                
                logger.info("✓ PostgreSQL schema created successfully")
                return True
                
        except Exception as e:
            logger.error(f"✗ Failed to create PostgreSQL schema: {str(e)}")
            return False
    
    def migrate_table_data(self, table_name: str, batch_size: int = 1000) -> bool:
        """Migrate data from a single table."""
        try:
            logger.info(f"Migrating table: {table_name}")
            
            # Get table metadata
            sqlite_metadata = MetaData()
            sqlite_table = Table(table_name, sqlite_metadata, autoload_with=self.sqlite_engine)
            
            postgres_metadata = MetaData()
            postgres_table = Table(table_name, postgres_metadata, autoload_with=self.postgres_engine)
            
            # Count total records
            with self.sqlite_engine.connect() as sqlite_conn:
                total_count = sqlite_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            
            if total_count == 0:
                logger.info(f"  ✓ Table {table_name} is empty, skipping")
                return True
            
            logger.info(f"  Migrating {total_count} records from {table_name}")
            
            migrated_count = 0
            error_count = 0
            
            # Migrate data in batches
            for offset in range(0, total_count, batch_size):
                try:
                    # Fetch batch from SQLite
                    with self.sqlite_engine.connect() as sqlite_conn:
                        query = text(f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}")
                        sqlite_rows = sqlite_conn.execute(query).fetchall()
                    
                    if not sqlite_rows:
                        break
                    
                    # Convert rows to dictionaries
                    batch_data = []
                    for row in sqlite_rows:
                        row_dict = dict(row._mapping)
                        # Handle datetime conversion if needed
                        row_dict = self._convert_datetime_fields(row_dict, table_name)
                        batch_data.append(row_dict)
                    
                    # Insert batch into PostgreSQL
                    with self.postgres_engine.connect() as postgres_conn:
                        postgres_conn.execute(postgres_table.insert(), batch_data)
                        postgres_conn.commit()
                    
                    migrated_count += len(batch_data)
                    logger.info(f"  Progress: {migrated_count}/{total_count} records migrated")
                    
                except Exception as batch_error:
                    error_count += len(sqlite_rows) if 'sqlite_rows' in locals() else batch_size
                    logger.error(f"  ✗ Batch migration error for {table_name} (offset {offset}): {str(batch_error)}")
                    
                    # Try to migrate records individually in this batch
                    if 'batch_data' in locals():
                        individual_success = self._migrate_records_individually(postgres_table, batch_data, table_name)
                        migrated_count += individual_success
                        error_count -= individual_success
            
            success_rate = (migrated_count / total_count) * 100 if total_count > 0 else 100
            logger.info(f"  ✓ Table {table_name} migration completed: {migrated_count}/{total_count} records ({success_rate:.1f}%)")
            
            if error_count > 0:
                logger.warning(f"  ⚠ {error_count} records failed to migrate for table {table_name}")
            
            self.stats['records_migrated'] += migrated_count
            self.stats['errors'] += error_count
            
            return error_count == 0
            
        except Exception as e:
            logger.error(f"✗ Failed to migrate table {table_name}: {str(e)}")
            return False
    
    def _migrate_records_individually(self, postgres_table: Table, batch_data: List[Dict], table_name: str) -> int:
        """Migrate records one by one when batch fails."""
        success_count = 0
        
        for record in batch_data:
            try:
                with self.postgres_engine.connect() as postgres_conn:
                    postgres_conn.execute(postgres_table.insert(), [record])
                    postgres_conn.commit()
                success_count += 1
            except Exception as e:
                logger.error(f"    ✗ Individual record migration failed for {table_name}: {str(e)}")
                logger.debug(f"      Failed record: {record}")
        
        return success_count
    
    def _convert_datetime_fields(self, row_dict: Dict[str, Any], table_name: str) -> Dict[str, Any]:
        """Convert datetime fields for PostgreSQL compatibility."""
        # Define datetime fields for each table
        datetime_fields = {
            'users': ['created_at', 'updated_at', 'joining_date', 'date_of_birth'],
            'attendance_data': ['timestamp', 'created_at', 'updated_at'],
            'leave_requests': ['start_date', 'end_date', 'created_at', 'updated_at', 'approved_at'],
            'permission_requests': ['date', 'created_at', 'updated_at', 'approved_at'],
            'leave_balances': ['created_at', 'updated_at'],
            'user_activities': ['timestamp'],
            'paid_holidays': ['date', 'created_at', 'updated_at']
        }
        
        fields_to_convert = datetime_fields.get(table_name, [])
        
        for field in fields_to_convert:
            if field in row_dict and row_dict[field] is not None:
                # Handle various datetime formats
                value = row_dict[field]
                if isinstance(value, str):
                    try:
                        # Try parsing common datetime formats
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d']:
                            try:
                                row_dict[field] = datetime.strptime(value, fmt)
                                break
                            except ValueError:
                                continue
                    except:
                        # If parsing fails, keep original value
                        pass
        
        return row_dict
    
    def verify_migration(self) -> Dict[str, Any]:
        """Verify the migration by comparing record counts."""
        logger.info("Verifying migration...")
        
        verification_results = {}
        tables = self.get_table_dependencies()
        
        for table_name in tables:
            try:
                # Count records in SQLite
                with self.sqlite_engine.connect() as sqlite_conn:
                    sqlite_count = sqlite_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                
                # Count records in PostgreSQL
                with self.postgres_engine.connect() as postgres_conn:
                    postgres_count = postgres_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                
                verification_results[table_name] = {
                    'sqlite_count': sqlite_count,
                    'postgres_count': postgres_count,
                    'match': sqlite_count == postgres_count
                }
                
                status = "✓" if sqlite_count == postgres_count else "✗"
                logger.info(f"  {status} {table_name}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")
                
            except Exception as e:
                verification_results[table_name] = {
                    'error': str(e)
                }
                logger.error(f"  ✗ Verification failed for {table_name}: {str(e)}")
        
        return verification_results
    
    def run_migration(self, batch_size: int = 1000, verify: bool = True) -> bool:
        """Run the complete migration process."""
        self.stats['start_time'] = datetime.now()
        
        logger.info("=" * 60)
        logger.info("STARTING SQLITE TO POSTGRESQL MIGRATION")
        logger.info("=" * 60)
        
        try:
            # Step 1: Test connections
            if not self.test_connections():
                return False
            
            # Step 2: Create PostgreSQL schema
            if not self.create_postgres_schema():
                return False
            
            # Step 3: Get migration order
            tables = self.get_table_dependencies()
            
            # Step 4: Migrate each table
            failed_tables = []
            for table_name in tables:
                if self.migrate_table_data(table_name, batch_size):
                    self.stats['tables_migrated'] += 1
                else:
                    failed_tables.append(table_name)
            
            # Step 5: Verify migration
            verification_results = {}
            if verify:
                verification_results = self.verify_migration()
            
            # Step 6: Report results
            self.stats['end_time'] = datetime.now()
            duration = self.stats['end_time'] - self.stats['start_time']
            
            logger.info("=" * 60)
            logger.info("MIGRATION COMPLETED")
            logger.info("=" * 60)
            logger.info(f"Duration: {duration}")
            logger.info(f"Tables migrated: {self.stats['tables_migrated']}/{len(tables)}")
            logger.info(f"Records migrated: {self.stats['records_migrated']}")
            logger.info(f"Errors: {self.stats['errors']}")
            
            if failed_tables:
                logger.warning(f"Failed tables: {failed_tables}")
            
            success = len(failed_tables) == 0
            
            if success:
                logger.info("✓ Migration completed successfully!")
            else:
                logger.error("✗ Migration completed with errors")
            
            return success
            
        except Exception as e:
            logger.error(f"✗ Migration failed: {str(e)}")
            return False
        
        finally:
            # Clean up connections
            self.sqlite_session.close()
            self.postgres_session.close()
    
    def cleanup_postgres_data(self) -> bool:
        """Clean up existing data in PostgreSQL (use with caution!)."""
        try:
            logger.warning("Cleaning up existing PostgreSQL data...")
            
            tables = self.get_table_dependencies()
            tables.reverse()  # Delete in reverse order to handle foreign keys
            
            with self.postgres_engine.connect() as conn:
                # Disable foreign key checks temporarily
                conn.execute(text("SET session_replication_role = replica;"))
                
                for table_name in tables:
                    conn.execute(text(f"DELETE FROM {table_name}"))
                    logger.info(f"  Cleared table: {table_name}")
                
                # Re-enable foreign key checks
                conn.execute(text("SET session_replication_role = DEFAULT;"))
                conn.commit()
            
            logger.info("✓ PostgreSQL data cleanup completed")
            return True
            
        except Exception as e:
            logger.error(f"✗ PostgreSQL cleanup failed: {str(e)}")
            return False


def main():
    """Main migration function."""
    # Configuration
    config = Config()
    
    # Database URIs
    sqlite_uri = config.SQLALCHEMY_DATABASE_URI
    postgres_uri = config.POSTGRES_DATABASE_URI
    
    logger.info(f"SQLite URI: {sqlite_uri}")
    logger.info(f"PostgreSQL URI: {postgres_uri.replace(postgres_uri.split('@')[0].split(':')[-1], '***')}")  # Hide password
    
    # Create migrator
    migrator = SQLiteToPostgresMigrator(sqlite_uri, postgres_uri)
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Migrate SQLite database to PostgreSQL')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for migration (default: 1000)')
    parser.add_argument('--no-verify', action='store_true', help='Skip verification step')
    parser.add_argument('--cleanup', action='store_true', help='Clean up existing PostgreSQL data before migration')
    parser.add_argument('--dry-run', action='store_true', help='Test connections only, do not migrate data')
    
    args = parser.parse_args()
    
    # Dry run - test connections only
    if args.dry_run:
        logger.info("DRY RUN MODE - Testing connections only")
        success = migrator.test_connections()
        sys.exit(0 if success else 1)
    
    # Cleanup existing data if requested
    if args.cleanup:
        confirm = input("Are you sure you want to delete all existing PostgreSQL data? (yes/no): ")
        if confirm.lower() == 'yes':
            if not migrator.cleanup_postgres_data():
                sys.exit(1)
        else:
            logger.info("Cleanup cancelled")
            sys.exit(0)
    
    # Run migration
    success = migrator.run_migration(
        batch_size=args.batch_size,
        verify=not args.no_verify
    )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

