import sqlite3
import os

def add_column():
    # Define database path - use relative path
    db_path = "everlast.db"
    
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        return
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("Adding columns for enhanced leave/permission management...")
        
        # Check if columns already exist in leave_requests
        cursor.execute("PRAGMA table_info(leave_requests)")
        leave_columns = [column[1] for column in cursor.fetchall()]
        
        if 'created_by' not in leave_columns:
            cursor.execute("ALTER TABLE leave_requests ADD COLUMN created_by INTEGER;")
            print("✅ Added created_by column to leave_requests table!")
        else:
            print("ℹ️ created_by column already exists in leave_requests")
            
        if 'is_auto_approved' not in leave_columns:
            cursor.execute("ALTER TABLE leave_requests ADD COLUMN is_auto_approved BOOLEAN DEFAULT 0;")
            print("✅ Added is_auto_approved column to leave_requests table!")
        else:
            print("ℹ️ is_auto_approved column already exists in leave_requests")
        
        # Check if columns already exist in permission_requests
        cursor.execute("PRAGMA table_info(permission_requests)")
        perm_columns = [column[1] for column in cursor.fetchall()]
        
        if 'created_by' not in perm_columns:
            cursor.execute("ALTER TABLE permission_requests ADD COLUMN created_by INTEGER;")
            print("✅ Added created_by column to permission_requests table!")
        else:
            print("ℹ️ created_by column already exists in permission_requests")
            
        if 'is_auto_approved' not in perm_columns:
            cursor.execute("ALTER TABLE permission_requests ADD COLUMN is_auto_approved BOOLEAN DEFAULT 0;")
            print("✅ Added is_auto_approved column to permission_requests table!")
        else:
            print("ℹ️ is_auto_approved column already exists in permission_requests")
        
        # Commit changes
        conn.commit()
        print("🎉 Database migration completed successfully!")

    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
    finally:
        # Close connection
        conn.close()

if __name__ == "__main__":
    add_column()