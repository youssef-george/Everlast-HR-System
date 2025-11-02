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
        logging.info(f"Starting server on port {Config.PORT}...")
        app.run(host='0.0.0.0', port=Config.PORT, debug=True)
        
    except KeyboardInterrupt:
        logging.info("Shutting down server...")
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")