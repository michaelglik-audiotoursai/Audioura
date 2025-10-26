#!/usr/bin/env python3
"""
Direct database update script for tour status.
"""
import sys
import psycopg2
from datetime import datetime

def update_tour_status(tour_id, status="completed"):
    """Update tour status directly in the database."""
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_tour_direct.py <tour_id> [status]")
        sys.exit(1)
    
    tour_id = sys.argv[1]
    status = "completed"
    
    if len(sys.argv) > 2:
        status = sys.argv[2]
    
    success = update_tour_status(tour_id, status)
    sys.exit(0 if success else 1)