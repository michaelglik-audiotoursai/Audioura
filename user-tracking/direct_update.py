"""
Direct update script for tour status.
"""
import psycopg2
from datetime import datetime
import sys

def update_tour_status(tour_id, status="completed"):
    """Update tour status directly in the database."""
    try:
        # Connect to PostgreSQL using the same connection string as the Docker container
        conn = psycopg2.connect(
            host="postgres-2",
            port=5432,
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Get current timestamp
        timestamp = datetime.now()
        
        # Execute update
        cur.execute(
            "UPDATE tour_requests SET status = %s, finished_at = %s WHERE tour_id = %s",
            (status, timestamp, tour_id)
        )
        
        # Commit the transaction
        conn.commit()
        rows_affected = cur.rowcount
        
        print(f"Updated {rows_affected} rows")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return rows_affected > 0
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python direct_update.py <tour_id> [status]")
        sys.exit(1)
    
    tour_id = sys.argv[1]
    status = "completed"
    
    if len(sys.argv) > 2:
        status = sys.argv[2]
    
    success = update_tour_status(tour_id, status)
    print(f"Update {'successful' if success else 'failed'}")
    sys.exit(0 if success else 1)