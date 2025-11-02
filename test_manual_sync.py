#!/usr/bin/env python3
"""
Test script to simulate manual sync from web interface
"""

import requests
import json
from datetime import datetime

def test_manual_sync():
    """Test the manual sync endpoint"""
    
    # Base URL
    base_url = "http://127.0.0.1:5000"
    
    # First, let's login to get a session
    print("🔐 Logging in...")
    login_data = {
        'email': 'admin@everlast.com',  # Replace with your admin email
        'password': 'admin123'  # Replace with your admin password
    }
    
    session = requests.Session()
    
    # Get login page to get CSRF token
    login_page = session.get(f"{base_url}/auth/login")
    if login_page.status_code != 200:
        print(f"❌ Failed to get login page: {login_page.status_code}")
        return
    
    # Extract CSRF token from login page
    csrf_token = None
    for line in login_page.text.split('\n'):
        if 'csrf-token' in line and 'content=' in line:
            csrf_token = line.split('content="')[1].split('"')[0]
            break
    
    if not csrf_token:
        print("❌ Could not find CSRF token")
        return
    
    print(f"✅ CSRF token found: {csrf_token[:20]}...")
    
    # Login
    login_response = session.post(f"{base_url}/auth/login", data={
        'email': login_data['email'],
        'password': login_data['password'],
        'csrf_token': csrf_token
    })
    
    if login_response.status_code != 302:  # Should redirect after login
        print(f"❌ Login failed: {login_response.status_code}")
        print(f"Response: {login_response.text[:200]}")
        return
    
    print("✅ Login successful!")
    
    # Now test manual sync
    print("\n🔄 Testing manual sync...")
    
    # Get new CSRF token for the sync request
    attendance_page = session.get(f"{base_url}/attendance/")
    if attendance_page.status_code != 200:
        print(f"❌ Failed to get attendance page: {attendance_page.status_code}")
        return
    
    # Extract CSRF token from attendance page
    csrf_token = None
    for line in attendance_page.text.split('\n'):
        if 'csrf-token' in line and 'content=' in line:
            csrf_token = line.split('content="')[1].split('"')[0]
            break
    
    if not csrf_token:
        print("❌ Could not find CSRF token for sync")
        return
    
    print(f"✅ CSRF token for sync: {csrf_token[:20]}...")
    
    # Make sync request
    sync_headers = {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf_token
    }
    
    sync_response = session.post(f"{base_url}/attendance/manual-sync", 
                                headers=sync_headers,
                                json={})
    
    print(f"📊 Sync response status: {sync_response.status_code}")
    
    if sync_response.status_code == 200:
        try:
            result = sync_response.json()
            print("✅ Sync successful!")
            print(f"   Status: {result.get('status', 'unknown')}")
            print(f"   Message: {result.get('message', 'No message')}")
            print(f"   Records added: {result.get('records_added', 0)}")
            print(f"   Records updated: {result.get('records_updated', 0)}")
        except json.JSONDecodeError:
            print("❌ Invalid JSON response")
            print(f"Response: {sync_response.text[:200]}")
    else:
        print(f"❌ Sync failed: {sync_response.status_code}")
        print(f"Response: {sync_response.text[:200]}")

if __name__ == "__main__":
    print("🚀 Testing Manual Sync from Web Interface")
    print("=" * 50)
    test_manual_sync()
