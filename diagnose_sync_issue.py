#!/usr/bin/env python3
"""
Diagnostic script to check why records aren't syncing to PostgreSQL
"""
import sys
from app import create_app
from extensions import db
from working_sync_service import working_sync_service
from sqlalchemy import text, inspect
from models import User, Department

def diagnose_sync():
    """Diagnose sync issues."""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("SYNC DIAGNOSTICS")
        print("=" * 60)
        
        # 1. Check sync service status
        print("\n1. Sync Service Status:")
        print(f"   Sync Enabled: {working_sync_service.sync_enabled}")
        print(f"   PostgreSQL Engine: {working_sync_service.postgres_engine is not None}")
        
        if not working_sync_service.sync_enabled:
            print("   [WARNING] Sync is DISABLED!")
            return
        
        if not working_sync_service.postgres_engine:
            print("   [WARNING] PostgreSQL engine not initialized!")
            return
        
        # 2. Test PostgreSQL connection
        print("\n2. PostgreSQL Connection:")
        try:
            if working_sync_service.test_postgres_connection():
                print("   [OK] PostgreSQL connection successful")
            else:
                print("   [ERROR] PostgreSQL connection FAILED")
                return
        except Exception as e:
            print(f"   [ERROR] Connection error: {str(e)}")
            return
        
        # 3. Check if tables exist in PostgreSQL
        print("\n3. Checking PostgreSQL Tables:")
        try:
            with working_sync_service.postgres_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name
                """))
                pg_tables = [row[0] for row in result]
                
                if not pg_tables:
                    print("   [WARNING] No tables found in PostgreSQL!")
                    print("   [SOLUTION] You need to create tables first")
                    print("   Run: python migrate_sqlite_to_postgres.py")
                else:
                    print(f"   [OK] Found {len(pg_tables)} tables:")
                    for table in pg_tables[:10]:
                        print(f"      - {table}")
                    
        except Exception as e:
            print(f"   ❌ Error checking tables: {str(e)}")
        
        # 4. Check SQLite vs PostgreSQL record counts
        print("\n4. Record Count Comparison:")
        try:
            # Check User table
            sqlite_users = db.session.query(User).count()
            print(f"   SQLite Users: {sqlite_users}")
            
            if pg_tables and 'users' in pg_tables:
                with working_sync_service.postgres_engine.connect() as conn:
                    result = conn.execute(text("SELECT COUNT(*) FROM users"))
                    pg_users = result.scalar()
                    print(f"   PostgreSQL Users: {pg_users}")
                    
                    if sqlite_users > pg_users:
                        print(f"   [WARNING] {sqlite_users - pg_users} users missing in PostgreSQL!")
            else:
                print("   [WARNING] Users table doesn't exist in PostgreSQL")
                
        except Exception as e:
            print(f"   ❌ Error comparing records: {str(e)}")
        
        # 5. Check event listeners
        print("\n5. Event Listeners:")
        print("   Checking if event listeners are registered...")
        # This is harder to check directly, but we can verify by looking at the setup
        
        # 6. Test creating a record
        print("\n6. Testing Record Creation Sync:")
        print("   Creating a test record...")
        try:
            # Get sync stats before
            stats_before = working_sync_service.get_sync_stats()
            print(f"   Sync stats before: {stats_before}")
            
            # Try to create a test user (but don't commit if it might conflict)
            print("   [INFO] To test: Create a new record through the app and check if it appears in PostgreSQL")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print("\n" + "=" * 60)
        print("RECOMMENDATIONS:")
        print("=" * 60)
        
        if not pg_tables:
            print("1. Create PostgreSQL tables first:")
            print("   python migrate_sqlite_to_postgres.py")
        else:
            print("1. If records aren't syncing, check:")
            print("   - Flask logs for sync errors")
            print("   - ENABLE_DB_SYNC environment variable is 'true'")
            print("   - PostgreSQL connection is working")
        
        print("2. To manually sync existing records:")
        print("   python migrate_sqlite_to_postgres.py")
        
        print("3. To check sync in real-time:")
        print("   - Watch Flask application logs")
        print("   - Look for 'Synced X changes' messages")
        
        print("\n" + "=" * 60)

if __name__ == '__main__':
    diagnose_sync()

