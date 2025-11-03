#!/usr/bin/env python3
"""
Setup biometric devices for EverLast ERP
"""
import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import DeviceSettings

def setup_devices():
    """Setup both biometric devices in the database"""
    app = create_app()
    
    with app.app_context():
        try:
            # Create tables if they don't exist
            db.create_all()
            
            # Device configurations
            devices_config = [
                {
                    'device_ip': '192.168.11.2',
                    'device_port': 4370,
                    'device_name': 'Ground Floor Device',
                    'is_active': True
                },
                {
                    'device_ip': '192.168.11.201',
                    'device_port': 4370,
                    'device_name': 'Upper Floor Device',
                    'is_active': True
                }
            ]
            
            devices_added = 0
            devices_updated = 0
            
            for device_config in devices_config:
                # Check if device already exists by NAME (not IP) to preserve existing IPs
                existing_device = DeviceSettings.query.filter_by(
                    device_name=device_config['device_name']
                ).first()
                
                if existing_device:
                    # Only update port and status if changed, NEVER update IP address
                    updated = False
                    if existing_device.device_port != device_config['device_port']:
                        existing_device.device_port = device_config['device_port']
                        updated = True
                    if existing_device.is_active != device_config['is_active']:
                        existing_device.is_active = device_config['is_active']
                        updated = True
                    if updated:
                        existing_device.updated_at = datetime.utcnow()
                        devices_updated += 1
                        print(f"[OK] Updated device: {device_config['device_name']} (IP preserved: {existing_device.device_ip}:{existing_device.device_port})")
                    else:
                        print(f"[SKIP] Device already exists: {device_config['device_name']} ({existing_device.device_ip}:{existing_device.device_port})")
                else:
                    # Create new device only if it doesn't exist
                    new_device = DeviceSettings(
                        device_ip=device_config['device_ip'],
                        device_port=device_config['device_port'],
                        device_name=device_config['device_name'],
                        is_active=device_config['is_active']
                    )
                    db.session.add(new_device)
                    devices_added += 1
                    print(f"[OK] Added device: {device_config['device_name']} ({device_config['device_ip']})")
            
            # Commit all changes
            db.session.commit()
            
            print(f"\n🎉 Device setup completed!")
            print(f"📊 Summary: {devices_added} devices added, {devices_updated} devices updated")
            
            # List all active devices
            print(f"\n📱 Active Devices:")
            active_devices = DeviceSettings.query.filter_by(is_active=True).all()
            for device in active_devices:
                print(f"  - {device.device_name}: {device.device_ip}:{device.device_port}")
            
        except Exception as e:
            print(f"❌ Error setting up devices: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    setup_devices()
