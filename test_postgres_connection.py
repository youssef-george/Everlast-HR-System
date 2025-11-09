"""
Test PostgreSQL connection - useful for troubleshooting DBeaver connection issues
"""
import psycopg2

POSTGRES_URI = 'postgresql://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres'

# Parse URI
DB_HOST = "196.219.160.253"
DB_PORT = 5444
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = "1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq"

print("Testing PostgreSQL Connection...")
print("=" * 60)
print(f"Host: {DB_HOST}")
print(f"Port: {DB_PORT}")
print(f"Database: {DB_NAME}")
print(f"User: {DB_USER}")
print("=" * 60)

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=10
    )
    
    print("\n✅ Connection successful!")
    
    cur = conn.cursor()
    
    # Get database version
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"\nPostgreSQL Version: {version.split(',')[0]}")
    
    # Get table count
    cur.execute("""
        SELECT COUNT(*) 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    table_count = cur.fetchone()[0]
    print(f"Tables in database: {table_count}")
    
    # List some tables
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name 
        LIMIT 10
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"\nSample tables: {', '.join(tables)}")
    
    cur.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Connection test PASSED!")
    print("=" * 60)
    print("\nFor DBeaver connection, use these settings:")
    print(f"  Host: {DB_HOST}")
    print(f"  Port: {DB_PORT}")
    print(f"  Database: {DB_NAME}")
    print(f"  Username: {DB_USER}")
    print(f"  Password: [your password]")
    print("  Driver: PostgreSQL")
    
except psycopg2.OperationalError as e:
    print(f"\n❌ Connection failed: {e}")
    print("\nPossible issues:")
    print("  1. Firewall blocking connection")
    print("  2. Database server not accessible")
    print("  3. Wrong host/port")
    print("  4. Network connectivity issue")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
