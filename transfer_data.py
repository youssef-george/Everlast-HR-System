import sqlite3 
 
 # Connect to old and new databases 
old_conn = sqlite3.connect('old.everlast.db') 
new_conn = sqlite3.connect('everlast.db') 
 
old_cursor = old_conn.cursor() 
new_cursor = new_conn.cursor() 
 
 # List of tables to transfer 
tables = ['users', 'attendance', 'departments', 'leaves', 'permissions']  # add/remove as needed 
 
for table in tables: 
     # Read from old database 
    old_cursor.execute(f"SELECT * FROM {table}") 
    rows = old_cursor.fetchall() 
 
     # Get column count 
    old_cursor.execute(f"PRAGMA table_info({table})") 
    columns = ','.join([col[1] for col in old_cursor.fetchall()]) 
    placeholders = ','.join(['?'] * len(rows[0])) if rows else '' 
 
     # Insert into new database 
    if rows: 
        new_cursor.executemany( 
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", 
            rows 
        ) 
        print(f"✅ Transferred {len(rows)} rows to '{table}'") 
 
new_conn.commit() 
old_conn.close() 
new_conn.close()