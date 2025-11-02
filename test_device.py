from zk import ZK
import time
from datetime import datetime

def test_device_connection():
    """Test connection to the fingerprint device and retrieve data"""
    print("Testing connection to fingerprint device...")
    print(f"Device IP: 192.168.11.2")
    print(f"Port: 4370")
    print("-" * 50)

    zk = ZK('192.168.11.2', port=4370, timeout=5)
    conn = None
    
    try:
        # Connect to device
        print("Attempting to connect...")
        conn = zk.connect()
        print("Connection successful!")
        
        # Get device info
        print("\nDevice Information:")
        print(f"Firmware Version: {conn.get_firmware_version()}")
        print(f"Serial Number: {conn.get_serialnumber()}")
        print(f"Platform: {conn.get_platform()}")
        print(f"Device Name: {conn.get_device_name()}")
        print(f"Face Function: {conn.get_face_fun_on()}")
        print(f"MAC Address: {conn.get_mac()}")
        
        # Get users
        print("\nRetrieving users...")
        users = conn.get_users()
        print(f"Found {len(users)} users:")
        for user in users:
            print(f"User ID: {user.user_id}, Name: {user.name}")
        
        # Get attendance
        print("\nRetrieving attendance records...")
        attendances = conn.get_attendance()
        print(f"Found {len(attendances)} attendance records:")
        for attendance in attendances[:5]:  # Show first 5 records
            print(f"User ID: {attendance.user_id}, Timestamp: {attendance.timestamp}")
        
        if len(attendances) > 5:
            print(f"... and {len(attendances) - 5} more records")
            
        return True, "Connection test successful"
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        return False, str(e)
        
    finally:
        if conn:
            print("\nDisconnecting from device...")
            conn.disconnect()
            print("Disconnected successfully")

if __name__ == "__main__":
    success, message = test_device_connection()
    if not success:
        print(f"\nTest failed: {message}")
    else:
        print("\nTest completed successfully") 