#!/usr/bin/env python3
import zipfile
import tempfile
import os
import psycopg2

def check_english_tour():
    # Get English tour ZIP data
    conn = psycopg2.connect(
        host="development-postgres-2-1",
        database="audiotours",
        user="admin", 
        password="password123"
    )
    
    cursor = conn.cursor()
    cursor.execute("SELECT audio_tour FROM audio_tours WHERE id = 5")
    zip_data = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    # Extract and check content
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "english_tour.zip")
        with open(zip_path, 'wb') as f:
            f.write(zip_data)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            files = zip_ref.namelist()
            print("Files in English ZIP:", files)
            
            # Check for audio files
            audio_files = [f for f in files if f.endswith('.mp3')]
            print(f"Audio files: {audio_files}")
            
            # Check HTML content
            html_files = [f for f in files if f.endswith('.html')]
            if html_files:
                html_content = zip_ref.read(html_files[0]).decode('utf-8')
                print(f"HTML content length: {len(html_content)}")
                print(f"HTML preview: {html_content[:200]}...")

if __name__ == "__main__":
    check_english_tour()