#!/usr/bin/env python3
"""
Backfill missing completed tours into audio_tours table.
This fixes the REQ-019 regression by indexing completed tours that have ZIP files
but were never added to audio_tours due to the missing tour update service call.
"""

import psycopg2
import os
import glob
from datetime import datetime

def connect_db():
    """Connect to the database."""
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours",
        user="admin",
        password="password123"
    )

def find_zip_for_tour(tour_id, request_string, tours_dir="/app/tours"):
    """Find the ZIP file for a given tour."""
    # Try to find ZIP files that might match this tour
    zip_files = glob.glob(os.path.join(tours_dir, "*.zip"))
    
    # Look for ZIP files with similar names
    location_keywords = []
    if "Newton" in request_string:
        location_keywords.extend(["newton", "Newton"])
    if "Center" in request_string or "Centre" in request_string:
        location_keywords.extend(["center", "centre", "Center", "Centre"])
    if "Library" in request_string:
        location_keywords.extend(["library", "Library"])
    if "Waban" in request_string:
        location_keywords.extend(["waban", "Waban"])
    
    # Find matching ZIP files
    matching_files = []
    for zip_file in zip_files:
        filename = os.path.basename(zip_file)
        if any(keyword in filename for keyword in location_keywords):
            matching_files.append(zip_file)
    
    # Return the most recent matching file
    if matching_files:
        matching_files.sort(key=os.path.getmtime, reverse=True)
        return matching_files[0]
    
    return None

def backfill_missing_tours():
    """Backfill missing completed tours into audio_tours table."""
    print(f"Starting backfill process: {datetime.now().isoformat()}")
    
    conn = connect_db()
    cur = conn.cursor()
    
    try:
        # Find completed tours that are missing from audio_tours
        print("Finding completed tours missing from audio_tours...")
        cur.execute("""
            SELECT tr.id, tr.tour_id, tr.request_string, tr.finished_at
            FROM tour_requests tr
            LEFT JOIN audio_tours at ON tr.request_string = at.request_string
            WHERE tr.status = 'completed' 
            AND at.request_string IS NULL
            AND tr.request_string LIKE '%Newton%'
            ORDER BY tr.finished_at DESC
        """)
        
        missing_tours = cur.fetchall()
        print(f"Found {len(missing_tours)} completed Newton tours missing from audio_tours")
        
        for tour_id_db, tour_id, request_string, finished_at in missing_tours:
            print(f"\nProcessing tour: {tour_id}")
            print(f"  Request: {request_string}")
            print(f"  Finished: {finished_at}")
            
            # Try to find the ZIP file for this tour
            zip_path = find_zip_for_tour(tour_id, request_string)
            if not zip_path:
                print(f"  ❌ No ZIP file found for tour {tour_id}")
                continue
            
            if not os.path.exists(zip_path):
                print(f"  ❌ ZIP file does not exist: {zip_path}")
                continue
            
            print(f"  ✅ Found ZIP file: {os.path.basename(zip_path)}")
            print(f"  📁 Size: {os.path.getsize(zip_path)} bytes")
            
            # Read the ZIP file
            with open(zip_path, 'rb') as f:
                zip_data = f.read()
            
            # Create tour name
            tour_name = f"{request_string} - walking Tour"
            if len(tour_name) > 255:
                tour_name = tour_name[:252] + "..."
            
            # Insert into audio_tours table
            try:
                cur.execute("""
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (tour_name, request_string, psycopg2.Binary(zip_data), 1, 42.3278, -71.205))
                
                print(f"  ✅ Successfully indexed tour in audio_tours")
                
                # Update tour_requests status to completed (in case it wasn't properly updated)
                cur.execute("""
                    UPDATE tour_requests 
                    SET status = 'completed', finished_at = COALESCE(finished_at, NOW())
                    WHERE tour_id = %s
                """, (tour_id,))
                
                conn.commit()
                print(f"  ✅ Updated tour_requests status")
                
            except Exception as e:
                print(f"  ❌ Error inserting tour: {e}")
                conn.rollback()
                continue
    
    except Exception as e:
        print(f"Error during backfill: {e}")
        conn.rollback()
    
    finally:
        cur.close()
        conn.close()
    
    print(f"\nBackfill process completed: {datetime.now().isoformat()}")

if __name__ == "__main__":
    backfill_missing_tours()