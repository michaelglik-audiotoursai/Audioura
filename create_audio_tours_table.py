"""
Script to create the audio_tours table in the database
"""
import psycopg2

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

if __name__ == "__main__":
    create_audio_tours_table()