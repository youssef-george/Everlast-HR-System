from app import create_app, db
from routes.attendance import sync_fingerprint

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        with app.test_request_context():
            print("Attempting to run sync_fingerprint...")
            try:
                result = sync_fingerprint()
                print("Sync result:", result)
            except Exception as e:
                print(f"An error occurred during sync: {e}")