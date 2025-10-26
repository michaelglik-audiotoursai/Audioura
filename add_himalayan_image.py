#!/usr/bin/env python3
import requests
import psycopg2
import sys

def download_and_add_image():
    # Download image
    print("Downloading Himalayan Bistro image...")
    image_url = "https://s3-media0.fl.yelpcdn.com/bphoto/0TLevkVpSNsk-X43CPGKhQ/o.jpg"
    
    try:
        response = requests.get(image_url, timeout=30)
        if response.status_code == 200:
            image_data = response.content
            print(f"Downloaded {len(image_data)} bytes")
        else:
            print(f"Failed to download image: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error downloading image: {e}")
        return False
    
    # Connect to database
    print("Connecting to database...")
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5433",
            database="audiotours",
            user="admin",
            password="password123"
        )
        cur = conn.cursor()
        
        # Update the Himalayan Bistro record with image
        print("Updating database...")
        cur.execute("""
            UPDATE treats 
            SET ad_image = %s 
            WHERE ad_name LIKE %s
        """, (psycopg2.Binary(image_data), '%Himalayan Bistro%'))
        
        rows_updated = cur.rowcount
        conn.commit()
        
        print(f"Updated {rows_updated} rows")
        
        cur.close()
        conn.close()
        
        return rows_updated > 0
        
    except Exception as e:
        print(f"Database error: {e}")
        return False

if __name__ == "__main__":
    success = download_and_add_image()
    if success:
        print("SUCCESS: Image added to Himalayan Bistro treat")
    else:
        print("FAILED: Could not add image")