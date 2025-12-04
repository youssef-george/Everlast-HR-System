#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import traceback
import os

# Redirect stdout and stderr to a file to capture all output
log_file = open('server_startup.log', 'w', encoding='utf-8')
sys.stdout = log_file
sys.stderr = log_file

try:
    print("=" * 70)
    print("Starting Flask Application")
    print("=" * 70)
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print()
    
    print("Step 1: Importing create_app...")
    from app import create_app
    print("✓ Import successful")
    
    print("Step 2: Creating app instance...")
    app = create_app()
    print("✓ App created successfully")
    
    print("Step 3: Starting Flask development server...")
    print("Server will run on http://127.0.0.1:5000")
    print("=" * 70)
    print()
    
    # Run the app
    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)
    
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    traceback.print_exc()
    log_file.close()
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
    log_file.close()
    sys.exit(1)
finally:
    log_file.close()
