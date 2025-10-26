"""
Store audio tours in the database with coordinates and ZIP files
"""
import os
import sys
import json
import psycopg2
import zipfile
import argparse
from datetime import datetime

def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):
    """
    Store an audio tour in the database with coordinates and ZIP file
    
    Args:
        tour_name: Name of the tour
        request_string: Original request string
        zip_path: Path to the ZIP file
        lat: Latitude (optional)
        lng: Longitude (optional)
    """
    try:
        # Read the ZIP file as binary data
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
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
        
        # Check if the audio_tours table has the necessary columns
        try:
            # Check if audio_tour column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'audio_tour'
            """)
            has_audio_tour = cur.fetchone() is not None
            
            # Check if lat/lng columns exist
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'lat'
            """)
            has_lat = cur.fetchone() is not None
            
            # Check if number_requested column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'number_requested'
            """)
            has_number_requested = cur.fetchone() is not None
            
            # Add missing columns if needed
            if not has_audio_tour:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN audio_tour BYTEA")
                print("Added audio_tour column")
            
            if not has_lat:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN lat DOUBLE PRECISION")
                cur.execute("ALTER TABLE audio_tours ADD COLUMN lng DOUBLE PRECISION")
                print("Added lat/lng columns")
            
            if not has_number_requested:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN number_requested INTEGER NOT NULL DEFAULT 0")
                print("Added number_requested column")
            
            conn.commit()
        except Exception as e:
            print(f"Error checking table structure: {e}")
            conn.rollback()
        
        # Check if tour already exists
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name = %s AND request_string = %s",
            (tour_name, request_string)
        )
        existing_tour = cur.fetchone()
        
        if existing_tour:
            # Update existing tour
            if has_audio_tour and has_lat and has_number_requested:
                cur.execute(
                    """
                    UPDATE audio_tours 
                    SET audio_tour = %s, number_requested = number_requested + 1, lat = %s, lng = %s
                    WHERE id = %s
                    """,
                    (psycopg2.Binary(zip_data), lat, lng, existing_tour[0])
                )
            else:
                # Fallback if columns don't exist
                cur.execute(
                    """
                    UPDATE audio_tours 
                    SET tour_name = %s, request_string = %s
                    WHERE id = %s
                    """,
                    (tour_name, request_string, existing_tour[0])
                )
            print(f"Updated existing tour: {tour_name}")
        else:
            # Insert new tour
            if has_audio_tour and has_lat and has_number_requested:
                cur.execute(
                    """
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (tour_name, request_string, psycopg2.Binary(zip_data), 1, lat, lng)
                )
            else:
                # Fallback if columns don't exist
                cur.execute(
                    """
                    INSERT INTO audio_tours (tour_name, request_string)
                    VALUES (%s, %s)
                    """,
                    (tour_name, request_string)
                )
            print(f"Inserted new tour: {tour_name}")
        
        # Commit the transaction
        conn.commit()
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"Error storing audio tour: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Store audio tour in database')
    parser.add_argument('--name', required=True, help='Tour name')
    parser.add_argument('--request', required=True, help='Original request string')
    parser.add_argument('--zip', required=True, help='Path to ZIP file')
    parser.add_argument('--lat', type=float, help='Latitude')
    parser.add_argument('--lng', type=float, help='Longitude')
    
    args = parser.parse_args()
    
    success = store_audio_tour(args.name, args.request, args.zip, args.lat, args.lng)
    
    if success:
        print("Audio tour stored successfully!")
    else:
        print("Failed to store audio tour")
        sys.exit(1)