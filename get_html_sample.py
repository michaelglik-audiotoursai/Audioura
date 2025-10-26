#!/usr/bin/env python3
"""
Get a larger sample of HTML content to understand structure
"""
import psycopg2
import zipfile
import tempfile
import os

def get_db_connection():
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def get_html_sample(tour_id=21):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT audio_tour FROM audio_tours 
        WHERE id = %s AND audio_tour IS NOT NULL
    """, (tour_id,))
    
    result = cur.fetchone()
    if not result:
        return
    
    audio_tour_data = result[0]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "tour.zip")
        with open(zip_path, 'wb') as f:
            f.write(audio_tour_data)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            html_content = zip_ref.read('index.html').decode('utf-8')
            
            # Print different sections
            print("=== HTML LENGTH ===")
            print(f"Total length: {len(html_content)} characters")
            
            print("\n=== FIRST 2000 CHARS ===")
            print(html_content[:2000])
            
            print("\n=== LOOKING FOR JAVASCRIPT ===")
            js_start = html_content.find('<script>')
            if js_start != -1:
                js_end = html_content.find('</script>', js_start)
                if js_end != -1:
                    js_content = html_content[js_start:js_end+9]
                    print(f"Found JavaScript section ({len(js_content)} chars)")
                    print(js_content[:1500])
            
            print("\n=== LOOKING FOR AUDIO DATA ===")
            if 'data:audio' in html_content:
                audio_start = html_content.find('data:audio')
                print(f"Found audio data at position {audio_start}")
                print(html_content[audio_start-100:audio_start+200])
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    get_html_sample()