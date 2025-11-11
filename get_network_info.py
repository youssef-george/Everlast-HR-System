#!/usr/bin/env python3
"""
Quick script to get network information for local deployment
"""

import socket
import os

def get_local_ip():
    """Get the local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
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
        ip_list = socket.gethostbyname_ex(hostname)[2]
        ips = [ip for ip in ip_list if not ip.startswith('127.')]
    except Exception:
        pass
    
    main_ip = get_local_ip()
    if main_ip and main_ip not in ips:
        ips.insert(0, main_ip)
    
    return ips if ips else ['127.0.0.1']

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    ips = get_all_ips()
    
    print("\n" + "=" * 60)
    print("EverLast ERP - Network Access Information")
    print("=" * 60)
    print(f"\n📍 Your Local IP Address(es):")
    for ip in ips:
        print(f"   • {ip}")
    
    print(f"\n🌐 Access from other devices on your network:")
    for ip in ips:
        print(f"   • http://{ip}:{port}")
    
    print(f"\n💻 Access from this machine:")
    print(f"   • http://localhost:{port}")
    print(f"   • http://127.0.0.1:{port}")
    print("\n" + "=" * 60 + "\n")

