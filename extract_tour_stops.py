#!/usr/bin/env python3
"""
Extract and analyze tour stops from HTML content
"""
import psycopg2
import zipfile
import tempfile
import os
import re
import json

def get_db_connection():
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def extract_tour_stops(tour_id=21):
    """Extract tour stops from HTML content"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT tour_name, audio_tour, request_string
        FROM audio_tours 
        WHERE id = %s AND audio_tour IS NOT NULL
    """, (tour_id,))
    
    result = cur.fetchone()
    if not result:
        return None
    
    tour_name, audio_tour_data, request_string = result
    
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "tour.zip")
        with open(zip_path, 'wb') as f:
            f.write(audio_tour_data)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            html_content = zip_ref.read('index.html').decode('utf-8')
            
            # Extract JavaScript data
            js_match = re.search(r'const tourData = ({.*?});', html_content, re.DOTALL)
            if js_match:
                tour_data_str = js_match.group(1)
                print("Found tourData JavaScript object")
                print("First 500 chars:", tour_data_str[:500])
                
                # Try to extract stops array
                stops_match = re.search(r'"stops":\s*(\[.*?\])', tour_data_str, re.DOTALL)
                if stops_match:
                    stops_str = stops_match.group(1)
                    print("\nFound stops array")
                    print("First 1000 chars:", stops_str[:1000])
                    
                    # Try to parse individual stops
                    stop_pattern = r'\{\s*"title":\s*"([^"]*)".*?"text":\s*"([^"]*)".*?"audio":\s*"([^"]*)".*?\}'
                    stops = re.findall(stop_pattern, stops_str, re.DOTALL)
                    
                    print(f"\nFound {len(stops)} stops:")
                    for i, (title, text, audio) in enumerate(stops[:3]):  # Show first 3
                        print(f"\nStop {i+1}:")
                        print(f"  Title: {title[:100]}...")
                        print(f"  Text: {text[:200]}...")
                        print(f"  Audio: {audio[:50]}...")
                    
                    return {
                        'tour_id': tour_id,
                        'tour_name': tour_name,
                        'request_string': request_string,
                        'stops': [{'title': title, 'text': text, 'audio': audio} for title, text, audio in stops]
                    }
            
            # Alternative: look for audio elements
            audio_pattern = r'<audio[^>]*id="audio(\d+)"[^>]*>.*?</audio>'
            audio_elements = re.findall(audio_pattern, html_content, re.DOTALL)
            print(f"\nFound {len(audio_elements)} audio elements")
            
            # Look for stop titles in HTML
            title_pattern = r'<h3[^>]*>([^<]+)</h3>'
            titles = re.findall(title_pattern, html_content)
            print(f"Found {len(titles)} h3 titles:", titles[:5])
    
    cur.close()
    conn.close()
    return None

if __name__ == "__main__":
    result = extract_tour_stops()
    if result:
        print(f"\nSuccessfully extracted {len(result['stops'])} stops from tour")
    else:
        print("Could not extract tour structure")