import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import User, AttendanceLog
from extensions import db

def find_unknown_fingerprint_ids():
    app = create_app()
    with app.app_context():
        # Get all fingerprint numbers from User Management
        fingerprint_numbers_in_management = {
            str(user.fingerprint_number) for user in User.query.filter(User.fingerprint_number.isnot(None)).all()
        }

        # --- IMPORTANT: REPLACE THIS LIST WITH YOUR ACTUAL FINGERPRINT NUMBERS FROM THE DEVICE ---
        # This is a sample list based on your screenshots (163, 164) and some existing users
        # You would get these numbers from your fingerprint device's export or raw data
        raw_fingerprint_numbers_from_device = {"147", "148", "154", "163", "164"}
        # ---------------------------------------------------------------------------------------

        unknown_fingerprint_numbers = raw_fingerprint_numbers_from_device - fingerprint_numbers_in_management

        if unknown_fingerprint_numbers:
            print("Fingerprint numbers found in your device data but not in User Management:")
            for fp_num in unknown_fingerprint_numbers:
                print(f"- {fp_num}")
        else:
            print("All fingerprint numbers from your device data are present in User Management.")

if __name__ == "__main__":
    print("Starting search for unknown fingerprint IDs...")
    find_unknown_fingerprint_ids()
    print("Done!")
