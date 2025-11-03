#!/usr/bin/env python3
"""
Quick PostgreSQL Connection Test
Test connection and show basic database info.
"""

import psycopg2
from sqlalchemy import create_engine, text
import sys

def test_direct_connection():
    """Test direct psycopg2 connection."""
    print("Testing direct PostgreSQL connection...")
    
    try:
        # Connection parameters
        conn_params = {
            'host': '196.219.160.253',
            'port': 5444,
            'database': 'postgres',
            'user': 'postgres',
            'password': '1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq',
            'sslmode': 'require'
        }
        
        # Connect
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"[OK] Connected successfully!")
        print(f"PostgreSQL version: {version}")
        
        # Show databases
        cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        databases = cursor.fetchall()
        print(f"Available databases: {[db[0] for db in databases]}")
        
        # Show tables in current database
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        print(f"Tables in 'postgres' database: {[table[0] for table in tables]}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Connection failed: {str(e)}")
        return False

def test_sqlalchemy_connection():
    """Test SQLAlchemy connection."""
    print("\nTesting SQLAlchemy connection...")
    
    try:
        # Create engine
        database_url = "postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require"
        
        engine = create_engine(database_url)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT current_database(), current_user, inet_server_addr(), inet_server_port();"))
            row = result.fetchone()
            
            print(f"[OK] SQLAlchemy connection successful!")
            print(f"Database: {row[0]}")
            print(f"User: {row[1]}")
            print(f"Server: {row[2]}:{row[3]}")
            
            # Count tables
            result = conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public';
            """))
            table_count = result.scalar()
            print(f"Public tables: {table_count}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] SQLAlchemy connection failed: {str(e)}")
        return False

def show_connection_info():
    """Show connection information for manual tools."""
    print("\n" + "=" * 60)
    print("CONNECTION INFORMATION")
    print("=" * 60)
    print("Host:     196.219.160.253")
    print("Port:     5444")
    print("Database: postgres")
    print("Username: postgres")
    print("Password: 1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq")
    print("SSL Mode: require")
    print("\nConnection String:")
    print("postgresql://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require")
    print("\npsql command:")
    print("psql -h 196.219.160.253 -p 5444 -U postgres -d postgres")

def main():
    """Main test function."""
    print("PostgreSQL Connection Test")
    print("=" * 40)
    
    # Test connections
    direct_ok = test_direct_connection()
    sqlalchemy_ok = test_sqlalchemy_connection()
    
    # Show connection info
    show_connection_info()
    
    # Summary
    print("\n" + "=" * 60)
    print("CONNECTION TEST SUMMARY")
    print("=" * 60)
    print(f"Direct Connection (psycopg2): {'[OK] SUCCESS' if direct_ok else '[ERROR] FAILED'}")
    print(f"SQLAlchemy Connection:       {'[OK] SUCCESS' if sqlalchemy_ok else '[ERROR] FAILED'}")
    
    if direct_ok and sqlalchemy_ok:
        print("\n[SUCCESS] All connections successful!")
        print("You can now use any PostgreSQL client to connect to your database.")
        print("\nRecommended tools:")
        print("- pgAdmin: https://www.pgadmin.org/")
        print("- DBeaver: https://dbeaver.io/")
        print("- DataGrip: https://www.jetbrains.com/datagrip/")
        print("- Or run: python view_postgres_data.py")
    else:
        print("\n[ERROR] Some connections failed. Check your network and credentials.")
    
    return direct_ok and sqlalchemy_ok

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

