#!/usr/bin/env python3
"""
Test script to run the EverLast ERP application
"""

try:
    print("Starting EverLast ERP application...")
    from app import create_app
    
    print("Creating Flask app...")
    app = create_app()
    
    print("App created successfully!")
    print("Starting server on http://0.0.0.0:5000")
    print("Press Ctrl+C to stop the server")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
    
except Exception as e:
    print(f"Error starting application: {str(e)}")
    import traceback
    traceback.print_exc()
