#!/usr/bin/env python
import socket
import sys
import time
from zk import ZK
import logging
import subprocess
import platform

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

DEVICE_IP = '192.168.11.2'
DEVICE_PORT = 4370

def ping_device():
    """Test if device is reachable via ping"""
    logging.info(f"Attempting to ping {DEVICE_IP}...")
    
    # Different ping command based on OS
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '3', DEVICE_IP]
    
    try:
        output = subprocess.check_output(command).decode()
        logging.info(f"Ping output:\n{output}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Ping failed: {str(e)}")
        return False

def test_socket_connection():
    """Test raw socket connection to device"""
    logging.info(f"Testing socket connection to {DEVICE_IP}:{DEVICE_PORT}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    
    try:
        result = sock.connect_ex((DEVICE_IP, DEVICE_PORT))
        if result == 0:
            logging.info("Socket connection successful")
            return True
        else:
            logging.error(f"Socket connection failed with error code: {result}")
            return False
    except Exception as e:
        logging.error(f"Socket connection error: {str(e)}")
        return False
    finally:
        sock.close()

def test_zk_connection():
    """Test ZK library connection and data retrieval"""
    logging.info("Testing ZK library connection...")
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=0, force_udp=False, ommit_ping=False)
    
    try:
        conn = zk.connect()
        if not conn:
            logging.error("Failed to establish ZK connection")
            return False
            
        logging.info("ZK connection successful")
        
        # Test basic device info
        logging.info("Retrieving device info...")
        logging.info(f"Firmware Version: {conn.get_firmware_version()}")
        logging.info(f"Serial Number: {conn.get_serialnumber()}")
        logging.info(f"Platform: {conn.get_platform()}")
        logging.info(f"Device Name: {conn.get_device_name()}")
        logging.info(f"Work Code: {conn.get_workcode()}")
        
        # Test attendance records
        logging.info("Retrieving attendance records...")
        attendances = conn.get_attendance()
        logging.info(f"Found {len(attendances)} attendance records")
        
        # Display last 5 records if available
        if attendances:
            logging.info("Last 5 attendance records:")
            for att in attendances[-5:]:
                logging.info(f"User ID: {att.user_id}, Timestamp: {att.timestamp}")
                
        return True
        
    except Exception as e:
        logging.error(f"ZK connection/operation error: {str(e)}")
        return False
        
    finally:
        if conn:
            conn.disconnect()
            logging.info("Disconnected from device")

def run_diagnostics():
    """Run all diagnostic tests"""
    logging.info("Starting device connectivity diagnostics...")
    
    results = {
        "ping": ping_device(),
        "socket": test_socket_connection(),
        "zk": test_zk_connection()
    }
    
    logging.info("\nDiagnostic Results:")
    logging.info("-" * 50)
    logging.info(f"Ping Test: {'✓ Passed' if results['ping'] else '✗ Failed'}")
    logging.info(f"Socket Test: {'✓ Passed' if results['socket'] else '✗ Failed'}")
    logging.info(f"ZK Connection: {'✓ Passed' if results['zk'] else '✗ Failed'}")
    logging.info("-" * 50)
    
    if all(results.values()):
        logging.info("All tests passed! Device is properly configured and accessible.")
    else:
        logging.error("Some tests failed. Please check the logs above for details.")
        
    return results

if __name__ == "__main__":
    run_diagnostics() 