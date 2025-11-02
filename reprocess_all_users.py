#!/usr/bin/env python3
"""
Script to trigger the reprocess-attendance API for all active users.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
from datetime import date
from app import create_app
from models import User

# NOTE: This script assumes your Flask app is running at http://127.0.0.1:5000
BASE_URL = "http://127.0.0.1:5000"

def get_active_users():
    """Fetches all active users from the database."""
    app = create_app()
    with app.app_context():
        active_users = User.query.filter_by(status='active').all()
        return [{'id': user.id, 'full_name': user.get_full_name()} for user in active_users]

def reprocess_user_attendance_api(user_id, start_date, end_date, session_cookie=None):
    """Calls the /reprocess-attendance API for a given user and date range."""
    url = f"{BASE_URL}/attendance/reprocess-attendance"
    payload = {
        'user_id': user_id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    }
    
    headers = {'Content-Type': 'application/json'}
    cookies = {'session': session_cookie} if session_cookie else None
    
    try:
        print(f"  Calling API for user {user_id} ({payload['start_date']} to {payload['end_date']})...")
        response = requests.post(url, json=payload, headers=headers, cookies=cookies)
        response.raise_for_status() # Raise an exception for HTTP errors
        
        result = response.json()
        if result.get('success'):
            print(f"    ✓ Success: {result.get('message')}")
        else:
            print(f"    ✗ Failed: {result.get('message')}")
            
    except requests.exceptions.HTTPError as e:
        print(f"    ✗ HTTP Error for user {user_id}: {e}")
        print(f"      Response: {e.response.text}")
    except requests.exceptions.ConnectionError as e:
        print(f"    ✗ Connection Error: Could not connect to the Flask server. Is it running? {e}")
    except Exception as e:
        print(f"    ✗ An unexpected error occurred for user {user_id}: {e}")

if __name__ == "__main__":
    print("Starting attendance reprocessing for all active users...")
    
    # IMPORTANT: You need to be logged in as an admin/product_owner to run this.
    # Obtain a session cookie from your browser after logging in and paste it here.
    # Example: 'your_session_cookie_value_here'
    # If you don't provide it, the API calls will likely fail with 401/403 errors.
    session_cookie = 'jhTsX9R01UNkP_rvoWmUfcT71efR6tXHkFEqvIWBWrs'    
    users_to_reprocess = get_active_users()
    
    if not users_to_reprocess:
        print("No active users found to reprocess.")
    else:
        print(f"Found {len(users_to_reprocess)} active users.")
        
        # Define the date range to reprocess
        start_date = date(2025, 9, 25)
        end_date = date(2025, 10, 23) # Extended to cover up to today's date, 2025-10-23
        
        for user in users_to_reprocess:
            print(f"Processing attendance for {user['full_name']} (ID: {user['id']})")
            reprocess_user_attendance_api(user['id'], start_date, end_date, session_cookie)
            
    print("Attendance reprocessing script finished.")
