#!/usr/bin/env python3
"""
PostgreSQL Database Viewer
View and explore your PostgreSQL database data.
"""

import os
import sys
from datetime import datetime
import pandas as pd

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def view_postgres_database():
    """View PostgreSQL database contents."""
    try:
        from flask import Flask
        from config import Config
        from extensions import db
        from working_sync_service import working_sync_service
        from models import User, Department, AttendanceData, LeaveRequest, PermissionRequest
        
        print("PostgreSQL Database Viewer")
        print("=" * 50)
        
        # Set up Flask app
        app = Flask(__name__)
        app.config.from_object(Config)
        
        # Initialize extensions
        db.init_app(app)
        working_sync_service.init_app(app)
        
        with app.app_context():
            # Test connection
            if not working_sync_service.test_postgres_connection():
                print("❌ Cannot connect to PostgreSQL database")
                return False
            
            print("✅ Connected to PostgreSQL database")
            print(f"Database: {working_sync_service.postgres_engine.url.database}")
            print(f"Host: {working_sync_service.postgres_engine.url.host}")
            print(f"Port: {working_sync_service.postgres_engine.url.port}")
            
            with working_sync_service.get_postgres_session() as pg_session:
                
                # 1. Show all tables and their record counts
                print("\n" + "=" * 50)
                print("TABLE OVERVIEW")
                print("=" * 50)
                
                tables_info = [
                    ("users", User),
                    ("departments", Department), 
                    ("attendance_data", AttendanceData),
                    ("leave_requests", LeaveRequest),
                    ("permission_requests", PermissionRequest)
                ]
                
                for table_name, model_class in tables_info:
                    try:
                        count = pg_session.query(model_class).count()
                        print(f"{table_name:20} | {count:6} records")
                    except Exception as e:
                        print(f"{table_name:20} | ERROR: {str(e)}")
                
                # 2. Show recent users
                print("\n" + "=" * 50)
                print("RECENT USERS (Last 10)")
                print("=" * 50)
                
                try:
                    recent_users = pg_session.query(User).order_by(User.id.desc()).limit(10).all()
                    
                    if recent_users:
                        print(f"{'ID':<5} | {'Name':<25} | {'Email':<30} | {'Role':<10} | {'Department'}")
                        print("-" * 80)
                        
                        for user in recent_users:
                            dept_name = user.department.name if user.department else "None"
                            print(f"{user.id:<5} | {user.get_full_name():<25} | {user.email:<30} | {user.role:<10} | {dept_name}")
                    else:
                        print("No users found")
                        
                except Exception as e:
                    print(f"Error fetching users: {str(e)}")
                
                # 3. Show recent attendance records
                print("\n" + "=" * 50)
                print("RECENT ATTENDANCE (Last 10)")
                print("=" * 50)
                
                try:
                    recent_attendance = pg_session.query(AttendanceData).order_by(AttendanceData.id.desc()).limit(10).all()
                    
                    if recent_attendance:
                        print(f"{'ID':<5} | {'Employee ID':<12} | {'Timestamp':<20} | {'Status':<12} | {'Device'}")
                        print("-" * 70)
                        
                        for record in recent_attendance:
                            timestamp_str = record.timestamp.strftime('%Y-%m-%d %H:%M:%S') if record.timestamp else 'N/A'
                            print(f"{record.id:<5} | {record.employee_id:<12} | {timestamp_str:<20} | {record.status:<12} | {record.device_id or 'N/A'}")
                    else:
                        print("No attendance records found")
                        
                except Exception as e:
                    print(f"Error fetching attendance: {str(e)}")
                
                # 4. Show departments
                print("\n" + "=" * 50)
                print("DEPARTMENTS")
                print("=" * 50)
                
                try:
                    departments = pg_session.query(Department).all()
                    
                    if departments:
                        print(f"{'ID':<5} | {'Name':<30} | {'Description'}")
                        print("-" * 60)
                        
                        for dept in departments:
                            description = (dept.description[:40] + '...') if dept.description and len(dept.description) > 40 else (dept.description or 'N/A')
                            print(f"{dept.id:<5} | {dept.name:<30} | {description}")
                    else:
                        print("No departments found")
                        
                except Exception as e:
                    print(f"Error fetching departments: {str(e)}")
                
                # 5. Show database statistics
                print("\n" + "=" * 50)
                print("DATABASE STATISTICS")
                print("=" * 50)
                
                try:
                    # Get total counts
                    total_users = pg_session.query(User).count()
                    total_attendance = pg_session.query(AttendanceData).count()
                    active_users = pg_session.query(User).filter(User.status == 'active').count()
                    
                    print(f"Total Users:           {total_users}")
                    print(f"Active Users:          {active_users}")
                    print(f"Total Attendance:      {total_attendance}")
                    
                    # Get latest activity
                    if total_attendance > 0:
                        latest_attendance = pg_session.query(AttendanceData).order_by(AttendanceData.timestamp.desc()).first()
                        if latest_attendance:
                            print(f"Latest Activity:       {latest_attendance.timestamp}")
                    
                except Exception as e:
                    print(f"Error getting statistics: {str(e)}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error viewing PostgreSQL database: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def export_to_csv():
    """Export PostgreSQL data to CSV files."""
    try:
        from flask import Flask
        from config import Config
        from extensions import db
        from working_sync_service import working_sync_service
        from models import User, Department, AttendanceData
        
        print("\nExporting PostgreSQL data to CSV files...")
        
        # Set up Flask app
        app = Flask(__name__)
        app.config.from_object(Config)
        
        # Initialize extensions
        db.init_app(app)
        working_sync_service.init_app(app)
        
        with app.app_context():
            with working_sync_service.get_postgres_session() as pg_session:
                
                # Export users
                users = pg_session.query(User).all()
                if users:
                    users_data = []
                    for user in users:
                        users_data.append({
                            'id': user.id,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'email': user.email,
                            'role': user.role,
                            'department_id': user.department_id,
                            'status': user.status,
                            'joining_date': user.joining_date,
                            'phone_number': user.phone_number,
                            'position': user.position
                        })
                    
                    df_users = pd.DataFrame(users_data)
                    df_users.to_csv('postgres_users.csv', index=False)
                    print(f"✓ Exported {len(users)} users to postgres_users.csv")
                
                # Export attendance
                attendance = pg_session.query(AttendanceData).order_by(AttendanceData.timestamp.desc()).limit(1000).all()
                if attendance:
                    attendance_data = []
                    for record in attendance:
                        attendance_data.append({
                            'id': record.id,
                            'employee_id': record.employee_id,
                            'timestamp': record.timestamp,
                            'status': record.status,
                            'device_id': record.device_id
                        })
                    
                    df_attendance = pd.DataFrame(attendance_data)
                    df_attendance.to_csv('postgres_attendance.csv', index=False)
                    print(f"✓ Exported {len(attendance)} attendance records to postgres_attendance.csv")
                
                # Export departments
                departments = pg_session.query(Department).all()
                if departments:
                    dept_data = []
                    for dept in departments:
                        dept_data.append({
                            'id': dept.id,
                            'name': dept.name,
                            'description': dept.description
                        })
                    
                    df_departments = pd.DataFrame(dept_data)
                    df_departments.to_csv('postgres_departments.csv', index=False)
                    print(f"✓ Exported {len(departments)} departments to postgres_departments.csv")
        
        return True
        
    except Exception as e:
        print(f"❌ Error exporting data: {str(e)}")
        return False

def run_custom_query():
    """Run a custom SQL query on PostgreSQL."""
    try:
        from flask import Flask
        from config import Config
        from extensions import db
        from working_sync_service import working_sync_service
        from sqlalchemy import text
        
        print("\nCustom Query Interface")
        print("=" * 30)
        print("Enter your SQL query (or 'quit' to exit):")
        
        # Set up Flask app
        app = Flask(__name__)
        app.config.from_object(Config)
        
        # Initialize extensions
        db.init_app(app)
        working_sync_service.init_app(app)
        
        with app.app_context():
            with working_sync_service.get_postgres_session() as pg_session:
                
                while True:
                    query = input("\nSQL> ").strip()
                    
                    if query.lower() in ['quit', 'exit', 'q']:
                        break
                    
                    if not query:
                        continue
                    
                    try:
                        result = pg_session.execute(text(query))
                        
                        if result.returns_rows:
                            rows = result.fetchall()
                            if rows:
                                # Print column headers
                                columns = result.keys()
                                print(" | ".join(str(col) for col in columns))
                                print("-" * (len(" | ".join(str(col) for col in columns))))
                                
                                # Print rows
                                for row in rows:
                                    print(" | ".join(str(val) for val in row))
                                
                                print(f"\n({len(rows)} rows)")
                            else:
                                print("No rows returned")
                        else:
                            print("Query executed successfully")
                            
                    except Exception as e:
                        print(f"Error: {str(e)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in custom query interface: {str(e)}")
        return False

def main():
    """Main function with menu."""
    while True:
        print("\n" + "=" * 60)
        print("PostgreSQL Database Viewer")
        print("=" * 60)
        print("1. View database overview")
        print("2. Export data to CSV")
        print("3. Run custom SQL query")
        print("4. Exit")
        print("=" * 60)
        
        choice = input("Select an option (1-4): ").strip()
        
        if choice == '1':
            view_postgres_database()
        elif choice == '2':
            export_to_csv()
        elif choice == '3':
            run_custom_query()
        elif choice == '4':
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please select 1-4.")

if __name__ == '__main__':
    main()

