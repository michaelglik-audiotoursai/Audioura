"""
Debug script to test database connection and table structure
"""
import psycopg2
import sys

def test_connection(host, port, database, user, password):
    """Test connection to the database"""
    try:
        print(f"Attempting to connect to database: {database} on {host}:{port} as {user}")
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        print("Connection successful!")
        
        # Create cursor
        cur = conn.cursor()
        
        # Check if audio_tours table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'audio_tours'
            )
        """)
        table_exists = cur.fetchone()[0]
        
        if table_exists:
            print("audio_tours table exists")
            
            # Check table structure
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours'
            """)
            columns = cur.fetchall()
            
            print("\nTable structure:")
            for column in columns:
                print(f"  {column[0]} ({column[1]})")
            
            # Check if there are any records
            cur.execute("SELECT COUNT(*) FROM audio_tours")
            count = cur.fetchone()[0]
            print(f"\nTotal records: {count}")
            
            if count > 0:
                # Show sample records
                cur.execute("SELECT id, tour_name, request_string FROM audio_tours LIMIT 3")
                records = cur.fetchall()
                print("\nSample records:")
                for record in records:
                    print(f"  ID: {record[0]}, Tour: {record[1]}, Request: {record[2]}")
        else:
            print("audio_tours table does not exist!")
            
            # Check what tables do exist
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = cur.fetchall()
            
            print("\nExisting tables:")
            for table in tables:
                print(f"  {table[0]}")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Connection error: {e}")
        return False

if __name__ == "__main__":
    # Try both possible host names
    hosts = ["postgres-2", "development-postgres-2-1"]
    port = 5432
    database = "audiotours"
    user = "admin"
    password = "password123"
    
    success = False
    
    for host in hosts:
        print(f"\nTrying host: {host}")
        if test_connection(host, port, database, user, password):
            success = True
            print(f"\nSuccessful connection with host: {host}")
            break
    
    if not success:
        print("\nFailed to connect to database with any host")
        sys.exit(1)
    
    print("\nConnection test completed")