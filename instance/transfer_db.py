import sqlite3

def transfer_database():
    # Define database paths
    source_db = r"C:\Users\Everlast\Downloads\EverLastERP\instance\old.everlast.db"
    target_db = r"C:\Users\Everlast\Downloads\EverLastERP\instance\everlast.db"
    
    # Connect to both databases
    source_conn = sqlite3.connect(source_db)
    target_conn = sqlite3.connect(target_db)
    
    source_cursor = source_conn.cursor()
    target_cursor = target_conn.cursor()

    try:
        # Get list of tables from source database
        source_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = source_cursor.fetchall()

        for table in tables:
            table_name = table[0]
            
            # Get table schema
            source_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';")
            schema = source_cursor.fetchone()[0]
            
            # Create table in target database
            target_cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
            target_cursor.execute(schema)
            
            # Copy data
            source_cursor.execute(f"SELECT * FROM {table_name};")
            rows = source_cursor.fetchall()
            
            if rows:
                # Get column count for the INSERT placeholder string
                column_count = len(rows[0])
                placeholders = ','.join(['?' for _ in range(column_count)])
                
                target_cursor.executemany(
                    f"INSERT INTO {table_name} VALUES ({placeholders});",
                    rows
                )
                print(f"Transferred {len(rows)} rows from table '{table_name}'")

        # Commit changes
        target_conn.commit()
        print("Database transfer completed successfully!")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        target_conn.rollback()
    
    finally:
        # Close connections
        source_conn.close()
        target_conn.close()

if __name__ == '__main__':
    transfer_database()
