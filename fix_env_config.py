#!/usr/bin/env python3
"""
Fix .env Configuration
Updates your .env file for the dual database setup.
"""

import os
import shutil
from datetime import datetime

def backup_env_file():
    """Create a backup of the current .env file."""
    if os.path.exists('.env'):
        backup_name = f'.env.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy('.env', backup_name)
        print(f"✅ Created backup: {backup_name}")
        return True
    return False

def create_corrected_env():
    """Create the corrected .env file content."""
    
    # Get the current directory for SQLite path
    current_dir = os.path.abspath(os.path.dirname(__file__))
    sqlite_path = os.path.join(current_dir, 'instance', 'everlast.db')
    sqlite_path_uri = sqlite_path.replace('\\', '/')
    
    corrected_env = f"""# EverLast ERP Environment Configuration

FLASK_ENV=development
SECRET_KEY=dev-secret-key-change-in-production
CSRF_SECRET=dev-csrf-secret-key-change-in-production

# Dual Database Configuration
# SQLite Database (Primary during transition)
SQLITE_DATABASE_URL=sqlite:///{sqlite_path_uri}

# PostgreSQL Database (Coolify - Sync Target)
POSTGRES_DATABASE_URL=postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require

# Database Sync Configuration
ENABLE_DB_SYNC=true
SYNC_BATCH_SIZE=100
SYNC_RETRY_ATTEMPTS=3
SYNC_RETRY_DELAY=5

# Flask Server Config
HOST=0.0.0.0
PORT=5000

# Ground Floor Device
DEVICE_IP=192.168.11.2
DEVICE_PORT=4370
DEVICE_URL=http://192.168.11.2/

# Upper Floor Device (Additional)
DEVICE_IP_2=192.168.11.201
DEVICE_PORT_2=4370
DEVICE_URL_2=http://192.168.11.201/

# Sync Config
SYNC_SECRET=everlast-sync-secret-key-2024
ENABLE_DIRECT_DEVICE_SYNC=true
"""
    
    return corrected_env

def show_differences():
    """Show what needs to be changed in the .env file."""
    print("🔍 ISSUES FOUND IN YOUR .env FILE:")
    print("=" * 50)
    
    print("❌ WRONG:")
    print("   DATABASE_URL=postgresql+psycopg2://...")
    print("   (This makes PostgreSQL the PRIMARY database)")
    
    print("\n✅ CORRECT:")
    print("   SQLITE_DATABASE_URL=sqlite:///...")
    print("   POSTGRES_DATABASE_URL=postgresql+psycopg2://...")
    print("   (This keeps SQLite as primary, PostgreSQL as sync target)")
    
    print("\n📝 MISSING VARIABLES:")
    print("   ENABLE_DB_SYNC=true")
    print("   SYNC_BATCH_SIZE=100") 
    print("   SYNC_RETRY_ATTEMPTS=3")
    print("   SYNC_RETRY_DELAY=5")

def update_env_file():
    """Update the .env file with correct configuration."""
    try:
        # Create backup
        backup_created = backup_env_file()
        
        # Get corrected content
        corrected_content = create_corrected_env()
        
        # Write new .env file
        with open('.env', 'w') as f:
            f.write(corrected_content)
        
        print("✅ Updated .env file with correct dual database configuration")
        
        if backup_created:
            print("✅ Your original .env file was backed up")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating .env file: {str(e)}")
        return False

def verify_config():
    """Verify the configuration is correct."""
    try:
        from config import Config
        
        config = Config()
        
        print("\n🔍 VERIFYING CONFIGURATION:")
        print("=" * 40)
        
        # Check primary database
        primary_db = config.SQLALCHEMY_DATABASE_URI
        print(f"Primary Database: {primary_db}")
        
        if primary_db.startswith('sqlite:///'):
            print("✅ SQLite is correctly set as primary database")
        else:
            print("❌ Primary database should be SQLite")
            return False
        
        # Check PostgreSQL sync database
        postgres_db = config.POSTGRES_DATABASE_URI
        print(f"PostgreSQL Sync: {postgres_db}")
        
        if postgres_db.startswith('postgresql'):
            print("✅ PostgreSQL is correctly configured for sync")
        else:
            print("❌ PostgreSQL sync database not configured")
            return False
        
        # Check sync settings
        sync_enabled = config.ENABLE_DB_SYNC
        print(f"Sync Enabled: {sync_enabled}")
        
        if sync_enabled:
            print("✅ Database sync is enabled")
        else:
            print("⚠ Database sync is disabled")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying configuration: {str(e)}")
        return False

def main():
    """Main function."""
    print("EverLast ERP - .env Configuration Fixer")
    print("=" * 50)
    
    # Show what's wrong
    show_differences()
    
    # Ask for confirmation
    print("\n" + "=" * 50)
    response = input("Do you want to fix your .env file? (y/n): ").lower().strip()
    
    if response in ['y', 'yes']:
        # Update .env file
        if update_env_file():
            # Verify the fix
            if verify_config():
                print("\n🎉 SUCCESS!")
                print("Your .env file has been corrected for dual database setup.")
                print("\nNext steps:")
                print("1. Test the configuration: python test_sync_fix.py")
                print("2. Start your Flask app: python app.py")
                print("3. Check sync status: http://localhost:5000/health")
            else:
                print("\n⚠ Configuration updated but verification failed.")
                print("Please check the error messages above.")
        else:
            print("\n❌ Failed to update .env file.")
    else:
        print("\n📝 Manual Update Required:")
        print("Please update your .env file with the correct variable names:")
        print("- Change DATABASE_URL to POSTGRES_DATABASE_URL")
        print("- Add SQLITE_DATABASE_URL for the primary database")
        print("- Add sync configuration variables")

if __name__ == '__main__':
    main()

