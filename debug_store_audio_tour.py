"""
Debug script to test storing audio tours in the database
"""
import psycopg2
import sys
import os

def create_audio_tours_table():
    """Create the audio_tours table if it doesn't exist"""
    try:
        # Connect to the database
        conn = psycopg2.connect(
            host="postgres-2",
            port=5432,
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'audio_tours'
            )
        """)
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            print("Creating audio_tours table...")
            cur.execute("""
                CREATE TABLE audio_tours (
                    id SERIAL PRIMARY KEY,
                    tour_name TEXT NOT NULL,
                    request_string TEXT NOT NULL,
                    audio_tour BYTEA,
                    number_requested INTEGER NOT NULL DEFAULT 0,
                    lat DOUBLE PRECISION,
                    lng DOUBLE PRECISION
                )
            """)
            print("Table created successfully")
        else:
            print("audio_tours table already exists")
            
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
        
        # Commit the transaction
        conn.commit()
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error creating table: {e}")
        return False

def store_test_audio_tour():
    """Store a test audio tour in the database"""
    try:
        # Create a test file if it doesn't exist
        test_file_path = "test_audio_tour.txt"
        if not os.path.exists(test_file_path):
            with open(test_file_path, "w") as f:
                f.write("This is a test audio tour file")
        
        # Read the test file as binary data
        with open(test_file_path, 'rb') as f:
            test_data = f.read()
        
        # Connect to the database
        conn = psycopg2.connect(
            host="postgres-2",
            port=5432,
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Insert test tour
        tour_name = "Test Tour"
        request_string = "Test Request"
        lat = 42.3601
        lng = -71.0589
        
        cur.execute(
            """
            INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (tour_name, request_string, psycopg2.Binary(test_data), 1, lat, lng)
        )
        
        # Commit the transaction
        conn.commit()
        
        # Verify the insertion
        cur.execute("SELECT COUNT(*) FROM audio_tours WHERE tour_name = %s", (tour_name,))
        count = cur.fetchone()[0]
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        if count > 0:
            print(f"Successfully stored test tour: {tour_name}")
            return True
        else:
            print("Failed to store test tour")
            return False
    except Exception as e:
        print(f"Error storing test tour: {e}")
        return False

if __name__ == "__main__":
    print("Testing database connection and audio tour storage...")
    
    # Create the table if it doesn't exist
    if create_audio_tours_table():
        print("\nTable setup successful")
    else:
        print("\nFailed to set up table")
        sys.exit(1)
    
    # Store a test audio tour
    if store_test_audio_tour():
        print("\nTest tour storage successful")
    else:
        print("\nFailed to store test tour")
        sys.exit(1)
    
    print("\nAll tests completed successfully")