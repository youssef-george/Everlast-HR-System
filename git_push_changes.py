#!/usr/bin/env python3
"""
Git Push Changes Script
Helps commit and push the dual database setup changes to repository.
"""

import os
import subprocess
import sys
from datetime import datetime

def run_command(command, description=""):
    """Run a command and return the result."""
    try:
        print(f"Running: {command}")
        if description:
            print(f"Purpose: {description}")
        
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Success: {description}")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
        else:
            print(f"❌ Error: {description}")
            if result.stderr.strip():
                print(f"Error: {result.stderr.strip()}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Exception running command: {str(e)}")
        return False

def check_git_status():
    """Check git status and show what files have changed."""
    print("🔍 Checking Git Status...")
    print("=" * 50)
    
    # Check if we're in a git repository
    if not os.path.exists('.git'):
        print("❌ Not a git repository. Initialize with: git init")
        return False
    
    # Get git status
    try:
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Git status failed: {result.stderr}")
            return False
        
        changes = result.stdout.strip()
        
        if not changes:
            print("✅ No changes to commit")
            return True
        
        print("📝 Files with changes:")
        for line in changes.split('\n'):
            if line.strip():
                status = line[:2]
                filename = line[3:]
                
                status_map = {
                    '??': '🆕 New file',
                    'M ': '✏️  Modified',
                    'A ': '➕ Added',
                    'D ': '🗑️  Deleted',
                    'R ': '🔄 Renamed',
                    'MM': '✏️  Modified (staged + unstaged)'
                }
                
                status_desc = status_map.get(status, f"❓ {status}")
                print(f"   {status_desc}: {filename}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking git status: {str(e)}")
        return False

def list_new_files():
    """List the new files we've created for the dual database setup."""
    new_files = [
        'working_sync_service.py',
        'sync_service.py', 
        'db_helpers.py',
        'migrate_sqlite_to_postgres.py',
        'enhanced_sync_service.py',
        'test_dual_database_setup.py',
        'test_sync_fix.py',
        'example_usage.py',
        'view_postgres_data.py',
        'test_postgres_connection.py',
        'test_db_connection.py',
        'fix_env_config.py',
        'git_push_changes.py',
        'DUAL_DATABASE_SETUP_GUIDE.md',
        'SYNC_FIX_SUMMARY.md'
    ]
    
    existing_files = []
    for file in new_files:
        if os.path.exists(file):
            existing_files.append(file)
    
    return existing_files

def create_commit_message():
    """Create a comprehensive commit message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    commit_message = f"""feat: Implement dual database setup with SQLite-PostgreSQL sync

🎯 Major Features Added:
- Dual database configuration (SQLite primary + PostgreSQL sync)
- Real-time synchronization service with SQLAlchemy event listeners
- Automatic data migration tools from SQLite to PostgreSQL
- Comprehensive testing and monitoring tools

📁 New Files:
- working_sync_service.py - Main synchronization service
- sync_service.py - Original sync service (backup)
- db_helpers.py - Database operation helpers with auto-sync
- migrate_sqlite_to_postgres.py - One-time migration script
- test_dual_database_setup.py - Comprehensive test suite
- test_sync_fix.py - Quick sync verification test
- view_postgres_data.py - PostgreSQL database viewer
- test_postgres_connection.py - Connection testing
- DUAL_DATABASE_SETUP_GUIDE.md - Complete setup guide
- SYNC_FIX_SUMMARY.md - Sync fix documentation

🔧 Modified Files:
- config.py - Updated for dual database configuration
- app.py - Integrated working sync service
- test_db_connection.py - Database connection testing

✨ Key Features:
- SQLite remains primary database for fast local operations
- PostgreSQL automatically synced for cloud/production readiness
- Thread-safe synchronization with proper error handling
- Batch operations support for performance
- Health monitoring endpoints
- Comprehensive migration and testing tools

🛡️ Data Safety:
- Existing SQLite data preserved
- Non-destructive sync (primary operations unaffected)
- Automatic retry mechanism for failed syncs
- Comprehensive error logging and recovery

📊 Monitoring:
- /health endpoint shows dual database status
- Real-time sync monitoring
- Connection pool status tracking
- Detailed logging for troubleshooting

Timestamp: {timestamp}
"""
    
    return commit_message

def add_files():
    """Add all relevant files to git."""
    print("📦 Adding files to git...")
    
    # Add modified files
    modified_files = ['config.py', 'app.py']
    for file in modified_files:
        if os.path.exists(file):
            if run_command(f'git add {file}', f"Adding modified file: {file}"):
                print(f"   ✅ Added: {file}")
    
    # Add new files
    new_files = list_new_files()
    for file in new_files:
        if run_command(f'git add {file}', f"Adding new file: {file}"):
            print(f"   ✅ Added: {file}")
    
    return True

def commit_changes():
    """Commit the changes with a comprehensive message."""
    print("💾 Committing changes...")
    
    commit_msg = create_commit_message()
    
    # Write commit message to file for complex message
    with open('commit_message.tmp', 'w', encoding='utf-8') as f:
        f.write(commit_msg)
    
    success = run_command('git commit -F commit_message.tmp', "Committing dual database setup")
    
    # Clean up temp file
    if os.path.exists('commit_message.tmp'):
        os.remove('commit_message.tmp')
    
    return success

def push_changes():
    """Push changes to remote repository."""
    print("🚀 Pushing to remote repository...")
    
    # Check if we have a remote
    result = subprocess.run(['git', 'remote', '-v'], capture_output=True, text=True)
    
    if not result.stdout.strip():
        print("⚠️  No remote repository configured.")
        print("To add a remote, run: git remote add origin <repository-url>")
        return False
    
    # Get current branch
    result = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True)
    current_branch = result.stdout.strip()
    
    if not current_branch:
        current_branch = 'main'  # Default branch
    
    print(f"📤 Pushing to branch: {current_branch}")
    
    return run_command(f'git push origin {current_branch}', f"Pushing to {current_branch}")

def show_summary():
    """Show a summary of what was committed."""
    print("\n" + "=" * 60)
    print("🎉 DUAL DATABASE SETUP - COMMIT SUMMARY")
    print("=" * 60)
    
    print("✅ Successfully committed dual database implementation:")
    print("   • SQLite primary database (preserves existing data)")
    print("   • PostgreSQL sync target (Coolify cloud database)")
    print("   • Real-time synchronization service")
    print("   • Comprehensive migration tools")
    print("   • Testing and monitoring utilities")
    
    print("\n📁 Files committed:")
    new_files = list_new_files()
    for file in new_files:
        print(f"   • {file}")
    
    print("\n🔧 Modified files:")
    print("   • config.py (dual database configuration)")
    print("   • app.py (sync service integration)")
    
    print("\n🚀 Next steps:")
    print("   1. Fix your .env file: python fix_env_config.py")
    print("   2. Test the setup: python test_sync_fix.py")
    print("   3. Start your app: python app.py")
    print("   4. Run migration: python migrate_sqlite_to_postgres.py")

def main():
    """Main function to handle git operations."""
    print("EverLast ERP - Git Push Dual Database Changes")
    print("=" * 60)
    
    # Check git status
    if not check_git_status():
        return False
    
    # Show what files we're about to commit
    print("\n📋 Files to be committed:")
    new_files = list_new_files()
    print(f"   • {len(new_files)} new files for dual database setup")
    print("   • config.py (updated configuration)")
    print("   • app.py (sync service integration)")
    
    # Ask for confirmation
    print("\n" + "=" * 60)
    response = input("Do you want to commit and push these changes? (y/n): ").lower().strip()
    
    if response not in ['y', 'yes']:
        print("❌ Operation cancelled")
        return False
    
    try:
        # Add files
        if not add_files():
            print("❌ Failed to add files")
            return False
        
        # Commit changes
        if not commit_changes():
            print("❌ Failed to commit changes")
            return False
        
        # Push changes
        push_success = push_changes()
        
        # Show summary
        show_summary()
        
        if push_success:
            print("\n🎉 Successfully pushed dual database setup to repository!")
        else:
            print("\n⚠️  Changes committed locally but push failed.")
            print("You may need to configure your remote repository or check network connection.")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during git operations: {str(e)}")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

