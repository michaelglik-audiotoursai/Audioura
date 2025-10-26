#!/usr/bin/env python3
"""
Examine the internal structure of a tour ZIP file to understand how stops are organized
"""
import psycopg2
import zipfile
import json
import tempfile
import os

def get_db_connection():
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def examine_tour_structure(tour_id=21):
    """Extract and examine a tour's internal structure"""
    print(f"Examining tour ID: {tour_id}")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT tour_name, audio_tour, request_string
        FROM audio_tours 
        WHERE id = %s AND audio_tour IS NOT NULL
    """, (tour_id,))
    
    result = cur.fetchone()
    if not result:
        print("Tour not found")
        return
    
    tour_name, audio_tour_data, request_string = result
    print(f"Tour: {tour_name}")
    print(f"Request: {request_string}")
    print(f"ZIP size: {len(audio_tour_data)} bytes")
    
    # Extract ZIP to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "tour.zip")
        with open(zip_path, 'wb') as f:
            f.write(audio_tour_data)
        
        # Examine ZIP contents
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            print(f"\nZIP Contents ({len(file_list)} files):")
            
            for file_name in sorted(file_list):
                file_info = zip_ref.getinfo(file_name)
                print(f"  {file_name} ({file_info.file_size} bytes)")
                
                # Extract and examine key files
                if file_name.endswith('.html'):
                    content = zip_ref.read(file_name).decode('utf-8')
                    print(f"\n--- HTML Content Preview ({file_name}) ---")
                    print(content[:500] + "..." if len(content) > 500 else content)
                
                elif file_name.endswith('.json'):
                    content = zip_ref.read(file_name).decode('utf-8')
                    print(f"\n--- JSON Content ({file_name}) ---")
                    try:
                        data = json.loads(content)
                        print(json.dumps(data, indent=2)[:1000] + "..." if len(content) > 1000 else json.dumps(data, indent=2))
                    except:
                        print(content[:500] + "..." if len(content) > 500 else content)
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    examine_tour_structure()