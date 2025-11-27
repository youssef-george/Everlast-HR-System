from app import create_app
from config import Config
import logging
import os

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set environment variables
    os.environ['FLASK_ENV'] = 'development'
    
    try:
        # Create and start the application
        app = create_app()
        
        # Get local IP for network access
        import socket
        def get_local_ip():
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
        
        local_ip = get_local_ip()
        port = Config.PORT
        
        # Print network access information
        import sys
        import io
        # Set UTF-8 encoding for console output
        if sys.stdout.encoding != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
        print("\n" + "=" * 70)
        print("Everlast HR System Server Starting")
        print("=" * 70)
        print(f"\n📍 Server Configuration:")
        print(f"   • Host: 0.0.0.0 (Listening on all network interfaces)")
        print(f"   • Port: {port}")
        print(f"\n🌐 Network Access URLs:")
        print(f"   • Local:     http://localhost:{port}")
        print(f"   • Local:     http://127.0.0.1:{port}")
        if local_ip != '127.0.0.1':
            print(f"   • Network:   http://{local_ip}:{port}")
        print(f"\n🔐 Login URL:")
        if local_ip != '127.0.0.1':
            print(f"   • http://{local_ip}:{port}/auth/login")
        print(f"   • http://localhost:{port}/auth/login")
        print(f"\n💡 To access from other devices on your network:")
        print(f"   1. Make sure Windows Firewall allows port {port}")
        print(f"   2. Use the Network URL above from any device on the same network")
        print(f"   3. All devices must be on the same local network (same router)")
        print("\n" + "=" * 70 + "\n")
        
        logging.info(f"Starting server on 0.0.0.0:{port}...")
        if local_ip != '127.0.0.1':
            logging.info(f"Network access: http://{local_ip}:{port}")
        logging.info(f"Local access: http://localhost:{port}")
        
        # Use debug=True but with reduced file watching to minimize restarts
        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=True,
            use_reloader=True,
            reloader_type='stat',  # Use stat-based reloader instead of watchdog
            threaded=True,  # Enable threading for better performance
            extra_files=[]  # Don't watch additional files
        )
        
    except KeyboardInterrupt:
        logging.info("Shutting down server...")
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")