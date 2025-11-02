#!/usr/bin/env python3
"""
EverLast ERP - Local Attendance Sync Agent

This script runs on the local network where biometric devices are located.
It connects to ZKTeco devices, fetches attendance logs, and syncs them 
to the cloud-deployed Flask application via secure API.

Author: EverLast ERP Team
Version: 1.0.0
"""

import os
import sys
import time
import json
import logging
import hashlib
import hmac
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import schedule
from zk import ZK
import configparser

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync_agent.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('SyncAgent')

class AttendanceSyncAgent:
    """Local sync agent for biometric device attendance logs"""
    
    def __init__(self, config_file='config.ini'):
        """Initialize the sync agent with configuration"""
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        # Server configuration
        self.server_url = self.config.get('server', 'url', fallback='https://your-app.coolify.domain')
        self.sync_secret = self.config.get('server', 'sync_secret', fallback='your-sync-secret-key')
        self.sync_endpoint = f"{self.server_url}/api/sync_logs"
        
        # Device configuration
        self.devices = self._load_device_config()
        
        # Sync configuration
        self.sync_interval = self.config.getint('sync', 'interval_minutes', fallback=5)
        self.batch_size = self.config.getint('sync', 'batch_size', fallback=100)
        self.max_retries = self.config.getint('sync', 'max_retries', fallback=3)
        
        logger.info(f"Sync Agent initialized with {len(self.devices)} devices")
        logger.info(f"Server URL: {self.server_url}")
        logger.info(f"Sync interval: {self.sync_interval} minutes")
    
    def _load_device_config(self) -> List[Dict]:
        """Load device configuration from config file"""
        devices = []
        
        # Get all sections that start with 'device_'
        for section in self.config.sections():
            if section.startswith('device_'):
                device = {
                    'id': section,
                    'name': self.config.get(section, 'name', fallback=section),
                    'ip': self.config.get(section, 'ip'),
                    'port': self.config.getint(section, 'port', fallback=4370),
                    'timeout': self.config.getint(section, 'timeout', fallback=30),
                    'password': self.config.get(section, 'password', fallback=''),
                    'enabled': self.config.getboolean(section, 'enabled', fallback=True)
                }
                
                if device['enabled']:
                    devices.append(device)
                    logger.info(f"Loaded device: {device['name']} ({device['ip']}:{device['port']})")
        
        return devices
    
    def _generate_signature(self, payload: bytes) -> str:
        """Generate HMAC signature for API authentication"""
        return hmac.new(
            self.sync_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
    
    def connect_to_device(self, device: Dict) -> Optional[ZK]:
        """Connect to a biometric device"""
        try:
            zk = ZK(device['ip'], port=device['port'], timeout=device['timeout'], password=device['password'])
            conn = zk.connect()
            logger.info(f"Connected to device: {device['name']} ({device['ip']})")
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to device {device['name']} ({device['ip']}): {str(e)}")
            return None
    
    def fetch_attendance_logs(self, device: Dict, conn) -> List[Dict]:
        """Fetch attendance logs from a device"""
        try:
            # Get attendance logs
            attendances = conn.get_attendance()
            logs = []
            
            # Convert to our format
            for attendance in attendances:
                log = {
                    'user_id': attendance.user_id,
                    'timestamp': attendance.timestamp.isoformat(),
                    'action': 'check_in' if attendance.punch == 0 else 'check_out'
                }
                logs.append(log)
            
            logger.info(f"Fetched {len(logs)} logs from device: {device['name']}")
            return logs
            
        except Exception as e:
            logger.error(f"Error fetching logs from device {device['name']}: {str(e)}")
            return []
    
    def sync_logs_to_server(self, device_id: str, logs: List[Dict]) -> bool:
        """Send logs to the cloud server"""
        if not logs:
            return True
        
        try:
            # Prepare payload
            payload_data = {
                'device_id': device_id,
                'logs': logs
            }
            payload_json = json.dumps(payload_data, separators=(',', ':'))
            payload_bytes = payload_json.encode('utf-8')
            
            # Generate signature
            signature = self._generate_signature(payload_bytes)
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'X-Sync-Signature': signature,
                'User-Agent': 'EverLast-Sync-Agent/1.0.0'
            }
            
            # Send request with retries
            for attempt in range(self.max_retries):
                try:
                    response = requests.post(
                        self.sync_endpoint,
                        data=payload_bytes,
                        headers=headers,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"Sync successful for {device_id}: {result.get('processed', 0)} processed, {result.get('skipped', 0)} skipped")
                        return True
                    else:
                        logger.error(f"Sync failed for {device_id}: HTTP {response.status_code} - {response.text}")
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"Network error syncing {device_id} (attempt {attempt + 1}): {str(e)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(5 * (attempt + 1))  # Exponential backoff
                        continue
                    
            return False
            
        except Exception as e:
            logger.error(f"Error syncing logs for {device_id}: {str(e)}")
            return False
    
    def sync_device(self, device: Dict) -> bool:
        """Sync attendance logs from a single device"""
        logger.info(f"Starting sync for device: {device['name']}")
        
        # Connect to device
        conn = self.connect_to_device(device)
        if not conn:
            return False
        
        try:
            # Fetch logs
            logs = self.fetch_attendance_logs(device, conn)
            
            if logs:
                # Process logs in batches
                for i in range(0, len(logs), self.batch_size):
                    batch = logs[i:i + self.batch_size]
                    success = self.sync_logs_to_server(device['id'], batch)
                    if not success:
                        logger.error(f"Failed to sync batch {i//self.batch_size + 1} for device {device['name']}")
                        return False
                    
                    # Small delay between batches
                    if i + self.batch_size < len(logs):
                        time.sleep(1)
            
            logger.info(f"Sync completed for device: {device['name']}")
            return True
            
        finally:
            # Always disconnect
            try:
                conn.disconnect()
                logger.debug(f"Disconnected from device: {device['name']}")
            except:
                pass
    
    def sync_all_devices(self):
        """Sync attendance logs from all configured devices"""
        logger.info("=== Starting sync cycle ===")
        start_time = datetime.now()
        
        success_count = 0
        total_devices = len(self.devices)
        
        for device in self.devices:
            try:
                if self.sync_device(device):
                    success_count += 1
                else:
                    logger.warning(f"Sync failed for device: {device['name']}")
                    
                # Small delay between devices
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Unexpected error syncing device {device['name']}: {str(e)}")
        
        duration = datetime.now() - start_time
        logger.info(f"=== Sync cycle completed: {success_count}/{total_devices} devices successful in {duration.total_seconds():.1f}s ===")
    
    def test_server_connection(self) -> bool:
        """Test connection to the cloud server"""
        try:
            # Test with empty payload
            test_payload = json.dumps({'test': True}).encode('utf-8')
            signature = self._generate_signature(test_payload)
            
            headers = {
                'Content-Type': 'application/json',
                'X-Sync-Signature': signature,
                'User-Agent': 'EverLast-Sync-Agent/1.0.0'
            }
            
            response = requests.post(
                self.sync_endpoint,
                data=test_payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code in [200, 400]:  # 400 is expected for test payload
                logger.info("Server connection test successful")
                return True
            else:
                logger.error(f"Server connection test failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Server connection test failed: {str(e)}")
            return False
    
    def run_once(self):
        """Run sync once"""
        self.sync_all_devices()
    
    def run_scheduler(self):
        """Run the sync agent with scheduled intervals"""
        logger.info(f"Starting sync agent scheduler (every {self.sync_interval} minutes)")
        
        # Test server connection first
        if not self.test_server_connection():
            logger.error("Cannot connect to server. Please check configuration.")
            return
        
        # Schedule sync
        schedule.every(self.sync_interval).minutes.do(self.sync_all_devices)
        
        # Run initial sync
        self.sync_all_devices()
        
        # Keep running
        while True:
            try:
                schedule.run_pending()
                time.sleep(30)  # Check every 30 seconds
            except KeyboardInterrupt:
                logger.info("Sync agent stopped by user")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {str(e)}")
                time.sleep(60)  # Wait a minute before retrying

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='EverLast ERP Attendance Sync Agent')
    parser.add_argument('--config', default='config.ini', help='Configuration file path')
    parser.add_argument('--once', action='store_true', help='Run sync once and exit')
    parser.add_argument('--test', action='store_true', help='Test server connection and exit')
    
    args = parser.parse_args()
    
    # Check if config file exists
    if not os.path.exists(args.config):
        logger.error(f"Configuration file not found: {args.config}")
        logger.info("Please create a config.ini file. See config.example.ini for reference.")
        sys.exit(1)
    
    # Initialize agent
    try:
        agent = AttendanceSyncAgent(args.config)
    except Exception as e:
        logger.error(f"Failed to initialize sync agent: {str(e)}")
        sys.exit(1)
    
    # Run based on arguments
    if args.test:
        success = agent.test_server_connection()
        sys.exit(0 if success else 1)
    elif args.once:
        agent.run_once()
    else:
        agent.run_scheduler()

if __name__ == '__main__':
    main()
