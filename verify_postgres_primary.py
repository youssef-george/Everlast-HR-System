#!/usr/bin/env python3
"""
Verify PostgreSQL is configured as primary database
"""
from app import create_app
from extensions import db
from models import User, AttendanceLog, DailyAttendance
from sqlalchemy import text

def verify_postgres_primary():
    """Verify PostgreSQL is the primary database."""
    app = create_app()
    
    print("=" * 70)
    print("POSTGRESQL PRIMARY DATABASE VERIFICATION")
    print("=" * 70)
    
    with app.app_context():
        # Check database URL
        db_url = str(db.engine.url)
        print(f"\n[1] Database Connection:")
        print(f"    URL: {db_url}")
        print(f"    Driver: {db.engine.url.drivername}")
        print(f"    Host: {db.engine.url.host}")
        print(f"    Database: {db.engine.url.database}")
        
        if 'postgresql' not in db_url.lower():
            print(f"\n[ERROR] Database is NOT PostgreSQL!")
            print(f"        Expected: PostgreSQL")
            print(f"        Actual: {db.engine.url.drivername}")
            return False
        else:
            print(f"\n[OK] Database is PostgreSQL")
        
        # Test connection
        print(f"\n[2] Testing Connection:")
        try:
            with db.engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.scalar()
                print(f"    [OK] Connection successful")
                print(f"    PostgreSQL Version: {version[:50]}...")
        except Exception as e:
            print(f"    [ERROR] Connection failed: {str(e)}")
            return False
        
        # Check table counts
        print(f"\n[3] Checking Table Data:")
        tables_to_check = [
            ('users', User),
            ('attendance_logs', AttendanceLog),
            ('daily_attendance', DailyAttendance),
        ]
        
        all_ok = True
        for table_name, model_class in tables_to_check:
            try:
                count = model_class.query.count()
                print(f"    {table_name}: {count} records [OK]")
            except Exception as e:
                print(f"    {table_name}: [ERROR] {str(e)}")
                all_ok = False
        
        # Verify no SQLite fallback
        print(f"\n[4] Checking for SQLite Fallback:")
        if 'sqlite' in db_url.lower():
            print(f"    [ERROR] SQLite detected in connection string!")
            all_ok = False
        else:
            print(f"    [OK] No SQLite connection detected")
        
        # Summary
        print("\n" + "=" * 70)
        if all_ok:
            print("[SUCCESS] PostgreSQL is configured as primary database!")
            print("=" * 70)
            return True
        else:
            print("[FAILED] Some checks failed. Please review above.")
            print("=" * 70)
            return False

if __name__ == '__main__':
    import sys
    success = verify_postgres_primary()
    sys.exit(0 if success else 1)

