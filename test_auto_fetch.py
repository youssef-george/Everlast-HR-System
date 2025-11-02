#!/usr/bin/env python3
"""
Test script for auto-fetch functionality
This script tests the API endpoints that the auto-fetch system uses
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5000"
TEST_USER_EMAIL = "erp@everlastwellness.com"
TEST_USER_PASSWORD = "Everlast@123"

class AutoFetchTester:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.csrf_token = None
        
    def login(self, email, password):
        """Login to get session and CSRF token"""
        print(f"🔐 Logging in as {email}...")
        
        # Get login page to get CSRF token
        login_page = self.session.get(f"{self.base_url}/auth/login")
        if login_page.status_code != 200:
            print(f"❌ Failed to get login page: {login_page.status_code}")
            return False
            
        # Extract CSRF token from the page
        import re
        csrf_match = re.search(r'name="csrf_token".*?value="([^"]+)"', login_page.text)
        if csrf_match:
            self.csrf_token = csrf_match.group(1)
            print(f"✅ CSRF token extracted: {self.csrf_token[:20]}...")
        else:
            print("⚠️  Could not extract CSRF token")
            
        # Login
        login_data = {
            'email': email,
            'password': password,
            'csrf_token': self.csrf_token
        }
        
        login_response = self.session.post(f"{self.base_url}/auth/login", data=login_data)
        if login_response.status_code == 200 and "dashboard" in login_response.url:
            print("✅ Login successful!")
            return True
        else:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
    
    def test_api_endpoint(self, endpoint, description):
        """Test an API endpoint"""
        print(f"\n🧪 Testing {description}...")
        print(f"   Endpoint: {endpoint}")
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}")
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                    return True
                except json.JSONDecodeError:
                    print(f"   Response (text): {response.text[:200]}...")
                    return False
            else:
                print(f"   Error: {response.text[:200]}...")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"   Exception: {e}")
            return False
    
    def test_all_endpoints(self):
        """Test all auto-fetch API endpoints"""
        print("🚀 Starting auto-fetch API tests...")
        print("=" * 60)
        
        # Test endpoints for different roles
        endpoints = [
            ("/api/dashboard/stats", "Dashboard Statistics"),
            ("/api/requests/recent", "Recent Requests"),
            ("/api/team/data", "Team Data (Manager/Admin)"),
            ("/api/approvals/pending", "Pending Approvals (Manager/Admin)"),
            ("/api/requests/all-pending", "All Pending Requests (Admin/Director)"),
            ("/api/analytics/departments", "Department Analytics (Admin/Director)"),
            ("/api/users/management", "User Management (Admin/Director)"),
            ("/api/analytics/company", "Company Analytics (Director)"),
            ("/api/requests/overview", "Requests Overview (Director)"),
            ("/api/leave/requests", "Leave Requests"),
            ("/api/leave/types", "Leave Types"),
            ("/api/leave/balances", "Leave Balances"),
            ("/api/attendance/data", "Attendance Data"),
            ("/api/attendance/stats", "Attendance Statistics"),
            ("/api/calendar/upcoming", "Upcoming Events")
        ]
        
        results = []
        for endpoint, description in endpoints:
            success = self.test_api_endpoint(endpoint, description)
            results.append((endpoint, description, success))
            time.sleep(0.5)  # Small delay between requests
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        successful = 0
        failed = 0
        
        for endpoint, description, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {description}")
            if success:
                successful += 1
            else:
                failed += 1
        
        print(f"\nTotal: {len(results)} tests")
        print(f"✅ Passed: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(successful/len(results)*100):.1f}%")
        
        return successful == len(results)
    
    def test_auto_fetch_js(self):
        """Test if auto-fetch JavaScript is properly loaded"""
        print("\n🧪 Testing auto-fetch JavaScript loading...")
        
        try:
            response = self.session.get(f"{self.base_url}/static/js/auto-fetch.js")
            if response.status_code == 200:
                print("✅ Auto-fetch JavaScript file is accessible")
                
                # Check for key functions
                js_content = response.text
                key_functions = [
                    "class AutoFetchSystem",
                    "performFetch",
                    "updateUI",
                    "fetchDashboardStats",
                    "fetchLeaveBalance"
                ]
                
                found_functions = []
                for func in key_functions:
                    if func in js_content:
                        found_functions.append(func)
                
                print(f"✅ Found {len(found_functions)}/{len(key_functions)} key functions")
                for func in found_functions:
                    print(f"   ✓ {func}")
                
                return len(found_functions) >= len(key_functions) * 0.8  # 80% threshold
            else:
                print(f"❌ Auto-fetch JavaScript file not accessible: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Exception loading JavaScript: {e}")
            return False

def main():
    """Main test function"""
    print("🔧 EverLast ERP Auto-Fetch System Test")
    print("=" * 50)
    print(f"Testing against: {BASE_URL}")
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    tester = AutoFetchTester(BASE_URL)
    
    # Login
    if not tester.login(TEST_USER_EMAIL, TEST_USER_PASSWORD):
        print("❌ Cannot proceed without login")
        return False
    
    # Test JavaScript loading
    js_success = tester.test_auto_fetch_js()
    
    # Test API endpoints
    api_success = tester.test_all_endpoints()
    
    # Final result
    print("\n" + "=" * 50)
    print("🎯 FINAL RESULT")
    print("=" * 50)
    
    if js_success and api_success:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Auto-fetch system is working correctly")
        return True
    else:
        print("⚠️  SOME TESTS FAILED")
        if not js_success:
            print("❌ JavaScript loading issues")
        if not api_success:
            print("❌ API endpoint issues")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
