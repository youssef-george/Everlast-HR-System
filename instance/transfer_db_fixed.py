import sqlite3

def get_column_names(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name});")
    return [column[1] for column in cursor.fetchall()]

def transfer_database():
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

        # First, delete all data from target database
        for table in tables:
            table_name = table[0]
            try:
                target_cursor.execute(f"DELETE FROM {table_name};")
            except sqlite3.OperationalError:
                print(f"Table {table_name} does not exist in target database. Creating it...")
                
                # Get table creation SQL
                source_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';")
                create_table_sql = source_cursor.fetchone()[0]
                target_cursor.execute(create_table_sql)

        # Now transfer data for each table
        for table in tables:
            table_name = table[0]
            print(f"\nTransferring table: {table_name}")
            
            # Get column names from both source and target
            source_columns = get_column_names(source_cursor, table_name)
            target_columns = get_column_names(target_cursor, table_name)
            
            # Find common columns
            common_columns = [col for col in source_columns if col in target_columns]
            
            if not common_columns:
                print(f"No matching columns found for table {table_name}, skipping...")
                continue
            
            # Create select and insert statements using only common columns
            select_cols = ", ".join(common_columns)
            placeholders = ", ".join(["?" for _ in common_columns])
            
            # Get data from source
            source_cursor.execute(f"SELECT {select_cols} FROM {table_name};")
            rows = source_cursor.fetchall()
            
            if rows:
                # Insert data into target
                target_cursor.executemany(
                    f"INSERT INTO {table_name} ({select_cols}) VALUES ({placeholders});",
                    rows
                )
                print(f"Transferred {len(rows)} rows")

        # Commit changes
        target_conn.commit()
        print("\nDatabase transfer completed successfully!")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        target_conn.rollback()
    
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == '__main__':
    transfer_database()
