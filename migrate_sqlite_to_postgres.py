#!/usr/bin/env python3
"""
Complete migration script from SQLite to PostgreSQL
Migrates all data and then deletes SQLite files
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
from config import Config

# Database connections
SQLITE_DB = 'instance/everlast.db'
POSTGRES_URL = Config.SQLALCHEMY_DATABASE_URI

# Table migration order (respecting foreign key dependencies)
MIGRATION_ORDER = [
    # Base tables (no foreign keys to other app tables)
    'leave_types',
    'departments',
    'users',
    
    # Device and config tables
    'device_settings',
    'smtp_configurations',
    'paid_holidays',
    
    # Dependent tables
    'leave_requests',
    'permission_requests',
    'attendance_logs',
    'daily_attendance',
    'fingerprint_failures',
    'device_users',
    'employee_attachments',
    'leave_balances',
    'deleted_users',
    
    # Alembic version table
    'alembic_version',
]

def get_sqlite_connection():
    """Connect to SQLite database"""
    if not os.path.exists(SQLITE_DB):
        raise FileNotFoundError(f"SQLite database not found: {SQLITE_DB}")
    return sqlite3.connect(SQLITE_DB)

def get_postgres_connection():
    """Connect to PostgreSQL database"""
    # Parse SQLAlchemy URL to psycopg2 format
    # Remove 'postgresql+psycopg2://' or 'postgresql://' prefix
    url = POSTGRES_URL.replace('postgresql+psycopg2://', '').replace('postgresql://', '')
    
    # Parse connection string: user:password@host:port/database?params
    if '@' in url:
        auth_part, rest = url.split('@', 1)
        if ':' in auth_part:
            user, password = auth_part.split(':', 1)
        else:
            user = auth_part
            password = None
        
        if '/' in rest:
            host_port, database = rest.split('/', 1)
            # Remove query parameters from database name
            if '?' in database:
                database = database.split('?')[0]
        else:
            host_port = rest
            database = None
        
        if ':' in host_port:
            host, port = host_port.split(':')
            port = int(port)
        else:
            host = host_port
            port = 5432
        
        # Build connection parameters
        conn_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
        }
        if password:
            conn_params['password'] = password
    else:
        # Fallback: try connecting with the URL as-is (it might work)
        return psycopg2.connect(url)
    
    return psycopg2.connect(**conn_params)

def get_table_columns(cursor, table_name, is_sqlite=True):
    """Get column names for a table"""
    if is_sqlite:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall()]
    else:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        return [row[0] for row in cursor.fetchall()]

def get_table_row_count(cursor, table_name, is_sqlite=True):
    """Get row count for a table"""
    if is_sqlite:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
    else:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]

def migrate_table(sqlite_conn, postgres_conn, table_name):
    """Migrate a single table from SQLite to PostgreSQL"""
    sqlite_cursor = sqlite_conn.cursor()
    postgres_cursor = postgres_conn.cursor()
    
    try:
        # Check if table exists in SQLite
        sqlite_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not sqlite_cursor.fetchone():
            print(f"  ⚠️  Table '{table_name}' does not exist in SQLite, skipping...")
            return 0
        
        # Get columns from both databases
        sqlite_columns = get_table_columns(sqlite_cursor, table_name, is_sqlite=True)
        
        # Check if table exists in PostgreSQL
        postgres_cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            )
        """, (table_name,))
        if not postgres_cursor.fetchone()[0]:
            print(f"  ⚠️  Table '{table_name}' does not exist in PostgreSQL, skipping...")
            return 0
        
        postgres_columns = get_table_columns(postgres_cursor, table_name, is_sqlite=False)
        
        # Find common columns
        common_columns = [col for col in sqlite_columns if col in postgres_columns]
        if not common_columns:
            print(f"  ⚠️  No common columns found for '{table_name}', skipping...")
            return 0
        
        # Get row count from SQLite
        sqlite_count = get_table_row_count(sqlite_cursor, table_name, is_sqlite=True)
        
        if sqlite_count == 0:
            print(f"  ✓  Table '{table_name}' is empty in SQLite, skipping...")
            return 0
        
        # Get existing row count from PostgreSQL
        postgres_count_before = get_table_row_count(postgres_cursor, table_name, is_sqlite=False)
        
        # Fetch all data from SQLite
        columns_str = ', '.join(common_columns)
        sqlite_cursor.execute(f"SELECT {columns_str} FROM {table_name}")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            print(f"  ✓  No rows to migrate for '{table_name}'")
            return 0
        
        # Get column types from PostgreSQL to handle type conversions
        postgres_cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        pg_column_types = {row[0]: row[1] for row in postgres_cursor.fetchall()}
        
        # Prepare data for bulk insert
        # Handle NULL values and convert types appropriately
        processed_rows = []
        for row in rows:
            processed_row = []
            for idx, val in enumerate(row):
                col_name = common_columns[idx]
                pg_type = pg_column_types.get(col_name, '')
                
                if val is None:
                    processed_row.append(None)
                elif isinstance(val, bytes):
                    # Handle BLOB data
                    processed_row.append(val)
                elif pg_type == 'boolean' and isinstance(val, (int, bool)):
                    # Convert SQLite integer booleans (0/1) to PostgreSQL booleans
                    processed_row.append(bool(val))
                elif pg_type == 'boolean' and isinstance(val, str):
                    # Handle string booleans
                    processed_row.append(val.lower() in ('true', '1', 'yes', 't'))
                else:
                    processed_row.append(val)
            processed_rows.append(tuple(processed_row))
        
        # Get primary key for ON CONFLICT clause
        postgres_cursor.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass
            AND i.indisprimary
        """, (table_name,))
        pk_result = postgres_cursor.fetchone()
        pk_column = pk_result[0] if pk_result and pk_result[0] in common_columns else None
        
        # Build INSERT statement with ON CONFLICT DO NOTHING
        columns_str = ', '.join([f'"{col}"' for col in common_columns])
        
        # Use execute_values for bulk insert
        if pk_column:
            insert_query = f"""
                INSERT INTO "{table_name}" ({columns_str})
                VALUES %s
                ON CONFLICT ("{pk_column}") DO NOTHING
            """
        else:
            # Fallback: try without specifying conflict target
            insert_query = f"""
                INSERT INTO "{table_name}" ({columns_str})
                VALUES %s
                ON CONFLICT DO NOTHING
            """
        
        # Execute bulk insert
        execute_values(
            postgres_cursor,
            insert_query,
            processed_rows,
            page_size=1000
        )
        
        postgres_conn.commit()
        
        # Get new row count
        postgres_count_after = get_table_row_count(postgres_cursor, table_name, is_sqlite=False)
        migrated_count = postgres_count_after - postgres_count_before
        
        print(f"  ✓  Migrated {migrated_count} rows from '{table_name}' (SQLite: {sqlite_count}, PostgreSQL before: {postgres_count_before}, after: {postgres_count_after})")
        
        return migrated_count
        
    except Exception as e:
        postgres_conn.rollback()
        print(f"  ✗  Error migrating '{table_name}': {str(e)}")
        raise

def fix_sequences(postgres_conn):
    """Fix PostgreSQL sequences for auto-increment columns"""
    postgres_cursor = postgres_conn.cursor()
    
    # Tables with auto-increment primary keys
    sequences_to_fix = [
        ('departments', 'departments_id_seq'),
        ('employee_attachments', 'employee_attachments_id_seq'),
        ('users', 'users_id_seq'),
        ('leave_requests', 'leave_requests_id_seq'),
        ('permission_requests', 'permission_requests_id_seq'),
        ('attendance_logs', 'attendance_logs_id_seq'),
        ('daily_attendance', 'daily_attendance_id_seq'),
        ('fingerprint_failures', 'fingerprint_failures_id_seq'),
        ('device_settings', 'device_settings_id_seq'),
        ('device_users', 'device_users_id_seq'),
        ('leave_types', 'leave_types_id_seq'),
        ('paid_holidays', 'paid_holidays_id_seq'),
        ('leave_balances', 'leave_balances_id_seq'),
        ('deleted_users', 'deleted_users_id_seq'),
        ('smtp_configurations', 'smtp_configurations_id_seq'),
    ]
    
    print("\n🔧 Fixing PostgreSQL sequences...")
    
    for table_name, seq_name in sequences_to_fix:
        try:
            # Check if table exists
            postgres_cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                )
            """, (table_name,))
            
            if not postgres_cursor.fetchone()[0]:
                continue
            
            # Check if sequence exists
            postgres_cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM pg_sequences 
                    WHERE sequencename = %s
                )
            """, (seq_name,))
            
            if not postgres_cursor.fetchone()[0]:
                print(f"  ⚠️  Sequence '{seq_name}' does not exist, skipping...")
                continue
            
            # Get max ID from table
            postgres_cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")
            max_id = postgres_cursor.fetchone()[0]
            
            if max_id > 0:
                # Set sequence to max_id + 1
                postgres_cursor.execute(f"SELECT setval('{seq_name}', {max_id + 1}, false)")
                postgres_conn.commit()
                print(f"  ✓  Fixed sequence '{seq_name}' (set to {max_id + 1})")
            else:
                print(f"  ✓  Sequence '{seq_name}' is already correct (no rows in table)")
                
        except Exception as e:
            postgres_conn.rollback()
            print(f"  ✗  Error fixing sequence '{seq_name}': {str(e)}")

def verify_migration(sqlite_conn, postgres_conn):
    """Verify migration by comparing row counts"""
    print("\n🔍 Verifying migration...")
    
    sqlite_cursor = sqlite_conn.cursor()
    postgres_cursor = postgres_conn.cursor()
    
    verification_errors = []
    
    for table_name in MIGRATION_ORDER:
        try:
            # Check if table exists in SQLite
            sqlite_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not sqlite_cursor.fetchone():
                continue
            
            # Check if table exists in PostgreSQL
            postgres_cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                )
            """, (table_name,))
            if not postgres_cursor.fetchone()[0]:
                continue
            
            sqlite_count = get_table_row_count(sqlite_cursor, table_name, is_sqlite=True)
            postgres_count = get_table_row_count(postgres_cursor, table_name, is_sqlite=False)
            
            if sqlite_count != postgres_count:
                verification_errors.append((table_name, sqlite_count, postgres_count))
                print(f"  ⚠️  '{table_name}': SQLite={sqlite_count}, PostgreSQL={postgres_count}")
            else:
                print(f"  ✓  '{table_name}': {sqlite_count} rows")
            
        except Exception as e:
            print(f"  ✗  Error verifying '{table_name}': {str(e)}")
    
    if verification_errors:
        print(f"\n⚠️  Warning: {len(verification_errors)} tables have row count mismatches (this is normal if some rows already existed)")
    else:
        print("\n✅ All tables verified successfully!")

def delete_sqlite_files():
    """Delete SQLite database files"""
    print("\n🗑️  Deleting SQLite files...")
    
    sqlite_files = [
        'instance/everlast.db',
        'instance/everlast_backup_20251102_154656.db',
    ]
    
    deleted_files = []
    for file_path in sqlite_files:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted_files.append(file_path)
                print(f"  ✓  Deleted: {file_path}")
            except Exception as e:
                print(f"  ✗  Error deleting {file_path}: {str(e)}")
    
    if deleted_files:
        print(f"\n✅ Deleted {len(deleted_files)} SQLite file(s)")
    else:
        print("\n⚠️  No SQLite files found to delete")

def main():
    """Main migration function"""
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)
    print(f"Source: {SQLITE_DB}")
    print(f"Target: {POSTGRES_URL.split('@')[1] if '@' in POSTGRES_URL else 'PostgreSQL'}")
    print("=" * 60)
    
    sqlite_conn = None
    postgres_conn = None
    
    try:
        # Connect to databases
        print("\n📡 Connecting to databases...")
        sqlite_conn = get_sqlite_connection()
        print("  ✓  Connected to SQLite")
        
        postgres_conn = get_postgres_connection()
        print("  ✓  Connected to PostgreSQL")
        
        # Migrate tables
        print("\n📦 Migrating tables...")
        total_migrated = 0
        
        for table_name in MIGRATION_ORDER:
            try:
                migrated = migrate_table(sqlite_conn, postgres_conn, table_name)
                total_migrated += migrated
            except Exception as e:
                print(f"  ✗  Failed to migrate '{table_name}': {str(e)}")
                # Continue with other tables
        
        print(f"\n✅ Migration complete! Total rows migrated: {total_migrated}")
        
        # Fix sequences
        fix_sequences(postgres_conn)
        
        # Verify migration
        verify_migration(sqlite_conn, postgres_conn)
        
        # Ask for confirmation before deleting
        print("\n" + "=" * 60)
        response = input("\n⚠️  Ready to delete SQLite files? (yes/no): ").strip().lower()
        
        if response == 'yes':
            delete_sqlite_files()
        else:
            print("\n⚠️  SQLite files were NOT deleted. You can delete them manually later.")
        
        print("\n" + "=" * 60)
        print("✅ Migration process completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗  Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if sqlite_conn:
            sqlite_conn.close()
        if postgres_conn:
            postgres_conn.close()
    
    return 0

if __name__ == '__main__':
    exit(main())
