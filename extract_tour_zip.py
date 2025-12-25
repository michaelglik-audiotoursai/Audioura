#!/usr/bin/env python3
"""
Extract Russian Tour ZIP from Database
Quick script to get the translated tour ZIP file
"""

import psycopg2
import sys

def extract_tour_zip(tour_id, output_filename):
    """Extract tour ZIP from database"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT audio_tour FROM audio_tours WHERE id = %s", (tour_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            zip_data = result[0]
            with open(output_filename, 'wb') as f:
                f.write(zip_data)
            print(f"✅ Extracted tour {tour_id} to {output_filename} ({len(zip_data)} bytes)")
            return True
        else:
            print(f"❌ Tour {tour_id} not found or has no ZIP data")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python extract_tour_zip.py TOUR_ID OUTPUT_FILE")
        print("Example: python extract_tour_zip.py 100 durant_kenrick_russian.zip")
        sys.exit(1)
    
    tour_id = int(sys.argv[1])
    output_file = sys.argv[2]
    
    success = extract_tour_zip(tour_id, output_file)
    sys.exit(0 if success else 1)