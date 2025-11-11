#!/usr/bin/env python3
"""
EverLast ERP - Local Network Deployment Script
This script helps deploy the Flask app on the local network
"""

import os
import sys
import socket
import subprocess
import platform
from app import create_app

def get_local_ip():
    """Get the local IP address of this machine"""
    try:
        # Connect to a remote address to determine local IP
        # This doesn't actually send data, just determines the route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to a public DNS server (doesn't actually connect)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def get_all_ips():
    """Get all local IP addresses"""
    ips = []
    try:
        hostname = socket.gethostname()
        # Get all IP addresses associated with this hostname
        ip_list = socket.gethostbyname_ex(hostname)[2]
        # Filter out loopback addresses
        ips = [ip for ip in ip_list if not ip.startswith('127.')]
    except Exception:
        pass
    
    # Also try the method above
    main_ip = get_local_ip()
    if main_ip and main_ip not in ips:
        ips.insert(0, main_ip)
    
    return ips if ips else ['127.0.0.1']

def check_port_available(port):
    """Check if a port is available"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result != 0  # Port is available if connection fails
    except Exception:
        return False

def print_network_info():
    """Print network deployment information"""
    print("=" * 60)
    print("EverLast ERP - Local Network Deployment")
    print("=" * 60)
    print()
    
    # Get IP addresses
    ips = get_all_ips()
    main_ip = ips[0] if ips else '127.0.0.1'
    
    # Get port
    port = int(os.environ.get("PORT", 5000))
    
    print(f"📍 Local IP Address(es):")
    for ip in ips:
        print(f"   • {ip}")
    print()
    
    print(f"🌐 Network Access URLs:")
    for ip in ips:
        print(f"   • http://{ip}:{port}")
    print()
    
    print(f"💻 Local Access URL:")
    print(f"   • http://localhost:{port}")
    print(f"   • http://127.0.0.1:{port}")
    print()
    
    # Check port availability
    if check_port_available(port):
        print(f"✅ Port {port} is available")
    else:
        print(f"⚠️  Port {port} may be in use")
    print()
    
    print("📋 Instructions:")
    print("   1. Make sure Windows Firewall allows connections on port", port)
    print("   2. Other devices on your network can access the app using:")
    print(f"      http://{main_ip}:{port}")
    print("   3. If you can't access from other devices:")
    print("      - Check Windows Firewall settings")
    print("      - Ensure all devices are on the same network")
    print("      - Try disabling firewall temporarily to test")
    print()
    print("=" * 60)
    print()

def configure_firewall_windows(port):
    """Configure Windows Firewall to allow the port"""
    if platform.system() != 'Windows':
        print("⚠️  Firewall configuration is only available on Windows")
        return False
    
    try:
        # Check if running as administrator
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        
        if not is_admin:
            print("⚠️  Administrator privileges required to configure firewall")
            print("   Please run this script as Administrator or configure manually:")
            print(f"   netsh advfirewall firewall add rule name=\"EverLast ERP\" dir=in action=allow protocol=TCP localport={port}")
            return False
        
        # Add firewall rule
        rule_name = f"EverLast ERP Port {port}"
        cmd = [
            'netsh', 'advfirewall', 'firewall', 'add', 'rule',
            f'name={rule_name}',
            'dir=in',
            'action=allow',
            'protocol=TCP',
            f'localport={port}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Firewall rule added successfully for port {port}")
            return True
        else:
            print(f"⚠️  Could not add firewall rule automatically")
            print(f"   Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"⚠️  Error configuring firewall: {str(e)}")
        return False

if __name__ == '__main__':
    # Get port from environment or use default
    port = int(os.environ.get("PORT", 5000))
    
    # Print network information
    print_network_info()
    
    # Ask about firewall configuration
    if platform.system() == 'Windows':
        print("🔧 Firewall Configuration:")
        response = input(f"   Configure Windows Firewall to allow port {port}? (y/n): ").strip().lower()
        if response == 'y':
            configure_firewall_windows(port)
        print()
    
    # Start the application
    print("🚀 Starting EverLast ERP server...")
    print("   Press Ctrl+C to stop the server")
    print()
    
    try:
        app = create_app()
        app.run(
            host='0.0.0.0',  # Listen on all network interfaces
            port=port,
            debug=True,
            threaded=True,  # Enable threading for better performance
            use_reloader=True
        )
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {str(e)}")
        sys.exit(1)

