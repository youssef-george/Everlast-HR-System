#!/usr/bin/env python3
"""
Test script to monitor database connection pool status
"""
import requests
import time
import json
from datetime import datetime

def test_health_endpoint():
    """Test the health endpoint to monitor connection pool status"""
    try:
        response = requests.get('http://localhost:5000/health', timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Health Check:")
            print(f"  Status: {data['status']}")
            print(f"  Database: {data['database']}")
            
            if 'pool_status' in data:
                pool = data['pool_status']
                print(f"  Pool Status:")
                print(f"    Pool Size: {pool['pool_size']}")
                print(f"    Checked In: {pool['checked_in']}")
                print(f"    Checked Out: {pool['checked_out']}")
                print(f"    Overflow: {pool['overflow']}")
                print(f"    Invalid: {pool['invalid']}")
                print(f"    Sync Running: {pool['sync_running']}")
                
                # Calculate utilization
                total_connections = pool['checked_in'] + pool['checked_out']
                utilization = (pool['checked_out'] / pool['pool_size']) * 100 if pool['pool_size'] > 0 else 0
                print(f"    Utilization: {utilization:.1f}%")
                
                # Warning if utilization is high
                if utilization > 80:
                    print("    ⚠️  WARNING: High connection pool utilization!")
                elif utilization > 60:
                    print("    ⚠️  CAUTION: Moderate connection pool utilization")
                else:
                    print("    ✅ Connection pool utilization is healthy")
            
            return True
        else:
            print(f"Health check failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to health endpoint: {str(e)}")
        return False

def monitor_connections(duration_minutes=5):
    """Monitor connection pool for a specified duration"""
    print(f"Starting connection pool monitoring for {duration_minutes} minutes...")
    print("Press Ctrl+C to stop early")
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    try:
        while time.time() < end_time:
            test_health_endpoint()
            print("-" * 50)
            time.sleep(30)  # Check every 30 seconds
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    
    print("Monitoring completed")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
            monitor_connections(duration)
        except ValueError:
            print("Usage: python test_connection_pool.py [duration_minutes]")
            print("Example: python test_connection_pool.py 5")
    else:
        # Single health check
        test_health_endpoint()




