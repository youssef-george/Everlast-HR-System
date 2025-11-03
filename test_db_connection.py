#!/usr/bin/env python3
"""
Test Database Connection
Simple script to test if the database connection works.
"""

import os
import sys

def test_sqlite_connection():
    """Test SQLite database connection."""
    try:
        # Import the config
        from config import Config
        
        print("Testing SQLite Database Connection")
        print("=" * 40)
        
        config = Config()
        db_uri = config.SQLALCHEMY_DATABASE_URI
        print(f"Database URI: {db_uri}")
        
        # Test with SQLAlchemy
        from sqlalchemy import create_engine, text
        
        print("Creating SQLAlchemy engine...")
        engine = create_engine(db_uri)
        
        print("Testing connection...")
        with engine.connect() as conn:
            # Test basic query
            result = conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"))
            table_count = result.scalar()
            print(f"✓ Connection successful! Found {table_count} tables in database.")
            
            # List some tables
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' LIMIT 10"))
            tables = [row[0] for row in result.fetchall()]
            print(f"Sample tables: {tables}")
        
        return True
        
    except Exception as e:
        print(f"✗ Database connection failed: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        return False

def test_flask_app():
    """Test Flask app initialization."""
    try:
        print("\nTesting Flask App Initialization")
        print("=" * 40)
        
        from flask import Flask
        from config import Config
        from extensions import db
        
        app = Flask(__name__)
        app.config.from_object(Config)
        
        print("Initializing database...")
        db.init_app(app)
        
        with app.app_context():
            print("Testing database connection in Flask context...")
            from sqlalchemy import text
            result = db.session.execute(text("SELECT 1"))
            print("✓ Flask database connection successful!")
        
        return True
        
    except Exception as e:
        print(f"✗ Flask app initialization failed: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        return False

def main():
    """Main test function."""
    print("Database Connection Test")
    print("=" * 50)
    
    # Test 1: Direct SQLite connection
    sqlite_ok = test_sqlite_connection()
    
    # Test 2: Flask app initialization
    flask_ok = test_flask_app()
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"SQLite Connection: {'✓ PASS' if sqlite_ok else '✗ FAIL'}")
    print(f"Flask App Init:    {'✓ PASS' if flask_ok else '✗ FAIL'}")
    
    if sqlite_ok and flask_ok:
        print("\n🎉 All tests passed! Your database connection is working.")
        print("You can now start your Flask application.")
    else:
        print("\n❌ Some tests failed. Please check the error messages above.")
    
    return sqlite_ok and flask_ok

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

