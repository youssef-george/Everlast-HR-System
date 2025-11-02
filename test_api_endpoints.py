#!/usr/bin/env python3
"""
Test script for auto-fetch API endpoints
Run this to verify that all API endpoints are working correctly
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5000"  # Adjust if your server runs on different port
TEST_USER = {
    "email": "admin@everlast.com",  # Adjust based on your test user
    "password": "admin123"  # Adjust based on your test user password
}

def test_login():
    """Test login and return session"""
    print("🔐 Testing login...")
    
    session = requests.Session()
    
    # Get login page first to get CSRF token
    login_page = session.get(f"{BASE_URL}/auth/login")
    if login_page.status_code != 200:
        print(f"❌ Failed to get login page: {login_page.status_code}")
        return None
    
    # Extract CSRF token (simplified - in real app you'd parse HTML)
    csrf_token = "test-token"  # You might need to extract this properly
    
    # Login
    login_data = {
        "email": TEST_USER["email"],
        "password": TEST_USER["password"],
        "csrf_token": csrf_token
    }
    
    login_response = session.post(f"{BASE_URL}/auth/login", data=login_data)
    
    if login_response.status_code == 200:
        print("✅ Login successful")
        return session
    else:
        print(f"❌ Login failed: {login_response.status_code}")
        print(f"Response: {login_response.text}")
        return None

def test_api_endpoint(session, endpoint, description):
    """Test a single API endpoint"""
    print(f"🧪 Testing {description}...")
    
    try:
        response = session.get(f"{BASE_URL}{endpoint}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ {description}: {len(data) if isinstance(data, list) else 'OK'}")
            return True
        else:
            print(f"❌ {description}: HTTP {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ {description}: Exception - {str(e)}")
        return False

def main():
    """Run all API tests"""
    print("🚀 Starting API endpoint tests...")
    print(f"📡 Testing against: {BASE_URL}")
    print(f"👤 Test user: {TEST_USER['email']}")
    print("-" * 50)
    
    # Test login
    session = test_login()
    if not session:
        print("❌ Cannot proceed without login")
        sys.exit(1)
    
    # Define test endpoints
    endpoints = [
        ("/api/dashboard/stats", "Dashboard Statistics"),
        ("/api/leave/requests", "Leave Requests"),
        ("/api/leave/types", "Leave Types"),
        ("/api/leave/balances", "Leave Balances"),
        ("/api/attendance/records", "Attendance Records"),
        ("/api/attendance/stats", "Attendance Statistics"),
        ("/api/employees/list", "Employees List"),
        ("/api/departments/list", "Departments List"),
        ("/api/permission/requests", "Permission Requests"),
        ("/api/calendar/events", "Calendar Events"),
    ]
    
    # Test each endpoint
    results = []
    for endpoint, description in endpoints:
        success = test_api_endpoint(session, endpoint, description)
        results.append((endpoint, description, success))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, _, success in results if success)
    total = len(results)
    
    for endpoint, description, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {description}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Auto-fetch API is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the API endpoints and authentication.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
