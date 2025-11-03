#!/usr/bin/env python3
"""
Check SQLite database contents
"""
import sqlite3
import os

def check_database():
    db_path = 'instance/everlast.db'
    
    if not os.path.exists(db_path):
        print('❌ Database file not found!')
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print('📊 Database Tables:')
        for table in tables:
            print(f'  - {table[0]}')
        
        # Check users table
        try:
            cursor.execute('SELECT COUNT(*) FROM users;')
            user_count = cursor.fetchone()[0]
            print(f'👥 Users in database: {user_count}')
            
            # Show some user details
            cursor.execute('SELECT id, first_name, last_name, email, role FROM users LIMIT 5;')
            users = cursor.fetchall()
            print('📋 Sample Users:')
            for user in users:
                print(f'  - ID: {user[0]}, Name: {user[1]} {user[2]}, Email: {user[3]}, Role: {user[4]}')
        except Exception as e:
            print(f'❌ Error checking users table: {e}')
        
        # Check attendance logs
        try:
            cursor.execute('SELECT COUNT(*) FROM attendance_logs;')
            attendance_count = cursor.fetchone()[0]
            print(f'📋 Attendance records: {attendance_count}')
        except Exception as e:
            print(f'❌ Error checking attendance_logs table: {e}')
        
        # Check device settings
        try:
            cursor.execute('SELECT COUNT(*) FROM device_settings;')
            device_count = cursor.fetchone()[0]
            print(f'📱 Device settings: {device_count}')
        except Exception as e:
            print(f'❌ Error checking device_settings table: {e}')
        
        conn.close()
        
    except Exception as e:
        print(f'❌ Database error: {e}')

if __name__ == '__main__':
    check_database()

