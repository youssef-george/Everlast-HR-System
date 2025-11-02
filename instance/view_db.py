import sqlite3
from tabulate import tabulate

def view_database(db_path, db_name):
    print(f"\n=== Database: {db_name} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        for table in tables:
            table_name = table[0]
            print(f"\n=== Table: {table_name} ===")
            
            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Get total count first
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            total_count = cursor.fetchone()[0]
            print(f"Total rows: {total_count}")
            
            if total_count > 0:
                # Get sample data (limited to first 3 rows to avoid overwhelming output)
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
                rows = cursor.fetchall()
                print(tabulate(rows, headers=columns, tablefmt='grid'))
            else:
                print("No data in table")
            print("\n")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    
    finally:
        conn.close()

if __name__ == '__main__':
    old_db = r"C:\Users\Everlast\Downloads\EverLastERP\instance\old.everlast.db"
    new_db = r"C:\Users\Everlast\Downloads\EverLastERP\instance\everlast.db"
    
    view_database(old_db, "OLD DATABASE")
    view_database(new_db, "NEW DATABASE")
