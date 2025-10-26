"""
Simple script to update tour status directly in the PostgreSQL database.
"""
import psycopg2
from datetime import datetime
import sys

def update_tour_status(tour_id, status="completed"):
    """Update tour status directly in the database."""
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            port=5433,  # Note: Using port 5433 as mapped in docker-compose.yml
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Get current timestamp
        timestamp = datetime.now().isoformat()
        
        # Execute update
        sql = f"UPDATE tour_requests SET status = '{status}', finished_at = '{timestamp}' WHERE tour_id = '{tour_id}'"
        print(f"Executing SQL: {sql}")
        cur.execute(sql)
        
        # Commit the transaction
        conn.commit()
        rows_affected = cur.rowcount
        
        if rows_affected > 0:
            print(f"Successfully updated {rows_affected} row(s)")
            
            # Query the updated record
            cur.execute(f"SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id = '{tour_id}'")
            row = cur.fetchone()
            if row:
                print(f"Updated record: id={row[0]}, tour_id={row[1]}, request={row[2][:30]}..., status={row[3]}, finished_at={row[4]}")
        else:
            print(f"No rows updated. Tour ID '{tour_id}' not found.")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return rows_affected > 0
        
    except Exception as e:
        print(f"Error: {e}")
        return False

def list_recent_tours(limit=5):
    """List recent tours in the database."""
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Execute query
        cur.execute(f"SELECT id, tour_id, request_string, status, finished_at FROM tour_requests ORDER BY id DESC LIMIT {limit}")
        
        # Fetch results
        rows = cur.fetchall()
        
        # Print results
        print(f"\nRecent tours (limit {limit}):")
        print("-" * 80)
        for row in rows:
            request_str = row[2][:40] + "..." if row[2] and len(row[2]) > 40 else row[2]
            print(f"ID: {row[0]}, Tour ID: {row[1] or 'None'}")
            print(f"Request: {request_str}")
            print(f"Status: {row[3]}, Finished At: {row[4] or 'None'}")
            print("-" * 80)
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python update_tour_status.py list [limit]")
        print("  python update_tour_status.py update <tour_id> [status]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        limit = 5
        if len(sys.argv) > 2:
            try:
                limit = int(sys.argv[2])
            except ValueError:
                print(f"Invalid limit: {sys.argv[2]}")
                sys.exit(1)
        list_recent_tours(limit)
    
    elif command == "update":
        if len(sys.argv) < 3:
            print("Error: Missing tour_id")
            sys.exit(1)
        
        tour_id = sys.argv[2]
        status = "completed"
        
        if len(sys.argv) > 3:
            status = sys.argv[3]
        
        success = update_tour_status(tour_id, status)
        sys.exit(0 if success else 1)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)