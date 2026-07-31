#!/usr/bin/env python3
import zipfile
import tempfile
import os
import psycopg2
from bs4 import BeautifulSoup

def test_russian_audio():
    # Get Russian tour ZIP data
    from db_connection import get_connection
    conn = get_connection()
    
    cursor = conn.cursor()
    cursor.execute("SELECT audio_tour FROM audio_tours WHERE id = 94")
    zip_data = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    # Extract and check content
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "russian_tour.zip")
        with open(zip_path, 'wb') as f:
            f.write(zip_data)
        
        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
            print("Files in ZIP:", zip_ref.namelist())
        
        # Check HTML content
        html_files = [f for f in os.listdir(extract_dir) if f.endswith('.html')]
        if html_files:
            html_file = os.path.join(extract_dir, html_files[0])
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            title = soup.find('title')
            paragraphs = soup.find_all('p')
            
            print(f"Title: {title.get_text() if title else 'No title'}")
            print(f"First paragraph: {paragraphs[0].get_text()[:100] if paragraphs else 'No paragraphs'}...")
            
            # Check for Russian text
            has_cyrillic = any(ord(char) >= 0x0400 and ord(char) <= 0x04FF for char in content)
            print(f"Contains Cyrillic text: {has_cyrillic}")

if __name__ == "__main__":
    test_russian_audio()