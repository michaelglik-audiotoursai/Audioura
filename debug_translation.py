#!/usr/bin/env python3
"""
Debug Translation Service - Step by step verification
"""
import boto3
import zipfile
import os
import re
import base64
import tempfile
import psycopg2
from bs4 import BeautifulSoup

class DebugTranslation:
    def __init__(self):
        self.translate_client = boto3.client('translate', region_name='us-east-1')
        self.polly_client = boto3.client('polly', region_name='us-east-1')
        
    def get_db_connection(self):
        return psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password123"
        )
    
    def step1_get_translation(self, text):
        """Step 1: Get Russian translation"""
        print(f"STEP 1 - ORIGINAL TEXT: {text}")
        
        response = self.translate_client.translate_text(
            Text=text[:5000],
            SourceLanguageCode='en',
            TargetLanguageCode='ru'
        )
        translated = response['TranslatedText']
        
        print(f"STEP 1 - RUSSIAN TRANSLATION: {translated}")
        return translated
    
    def step2_get_audio(self, text):
        """Step 2: Generate Russian audio"""
        print(f"STEP 2 - GENERATING AUDIO FOR: {text}")
        
        response = self.polly_client.synthesize_speech(
            Text=text[:3000],
            OutputFormat='mp3',
            VoiceId='Tatyana'
        )
        audio_bytes = response['AudioStream'].read()
        
        # Save audio file for verification
        audio_path = f'/tmp/russian_audio_{len(text)}.mp3'
        with open(audio_path, 'wb') as f:
            f.write(audio_bytes)
        
        print(f"STEP 2 - AUDIO SAVED: {audio_path} ({len(audio_bytes)} bytes)")
        return audio_bytes
    
    def step3_create_html(self, tour_id):
        """Step 3: Create HTML with Russian audio"""
        print(f"STEP 3 - PROCESSING TOUR {tour_id}")
        
        # Get original tour
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT tour_name, audio_tour FROM audio_tours WHERE id = %s", (tour_id,))
        result = cursor.fetchone()
        
        if not result:
            print("STEP 3 - ERROR: Tour not found")
            return None
            
        tour_name, zip_data = result
        print(f"STEP 3 - TOUR NAME: {tour_name}")
        print(f"STEP 3 - ORIGINAL ZIP SIZE: {len(zip_data)} bytes")
        
        # Extract original ZIP
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "original.zip")
            with open(zip_path, 'wb') as f:
                f.write(zip_data)
            
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find HTML file
            html_files = [f for f in os.listdir(extract_dir) if f.endswith('.html')]
            if not html_files:
                print("STEP 3 - ERROR: No HTML file found")
                return None
                
            html_file = os.path.join(extract_dir, html_files[0])
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            print(f"STEP 3 - ORIGINAL HTML SIZE: {len(html_content)} chars")
            
            # Find embedded audio
            audio_pattern = r'data:audio/[^;]+;base64,([A-Za-z0-9+/=]+)'
            audio_matches = re.findall(audio_pattern, html_content)
            print(f"STEP 3 - FOUND {len(audio_matches)} EMBEDDED AUDIO DATA URLs")
            
            # Extract text for translation - enhanced extraction
            soup = BeautifulSoup(html_content, 'html.parser')
            text_elements = []
            
            # Look for text in various elements
            for tag in ['p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                elements = soup.find_all(tag)
                for elem in elements:
                    text = elem.get_text().strip()
                    if text and len(text) > 10 and 'audio' not in text.lower():
                        text_elements.append(text)
            
            # If no elements found, extract from raw HTML
            if not text_elements:
                # Look for text patterns in the HTML
                text_patterns = re.findall(r'>([^<]{20,})<', html_content)
                for text in text_patterns:
                    clean_text = text.strip()
                    if clean_text and len(clean_text) > 20:
                        text_elements.append(clean_text)
            
            print(f"STEP 3 - FOUND {len(text_elements)} TEXT ELEMENTS")
            for i, text in enumerate(text_elements[:3]):  # Show first 3
                print(f"  TEXT {i+1}: {text[:100]}...")
            
            # Translate and generate audio for each text element
            updated_html = html_content
            for i, text in enumerate(text_elements[:3]):  # Process first 3
                print(f"\nPROCESSING TEXT ELEMENT {i+1}:")
                
                # Step 1: Translate
                russian_text = self.step1_get_translation(text)
                
                # Step 2: Generate audio
                russian_audio = self.step2_get_audio(russian_text)
                
                # Convert to base64
                russian_base64 = base64.b64encode(russian_audio).decode('utf-8')
                print(f"STEP 3 - RUSSIAN BASE64 AUDIO: {len(russian_base64)} chars")
                
                # Replace in HTML if we have enough audio matches
                if i < len(audio_matches):
                    original_data_url = f'data:audio/mp3;base64,{audio_matches[i]}'
                    russian_data_url = f'data:audio/mp3;base64,{russian_base64}'
                    updated_html = updated_html.replace(original_data_url, russian_data_url, 1)
                    print(f"STEP 3 - REPLACED AUDIO {i+1} IN HTML")
            
            # Save HTML for verification
            html_output_path = '/tmp/russian_index.html'
            with open(html_output_path, 'w', encoding='utf-8') as f:
                f.write(updated_html)
            
            print(f"STEP 3 - RUSSIAN HTML SAVED: {html_output_path}")
            print(f"STEP 3 - RUSSIAN HTML SIZE: {len(updated_html)} chars")
            
            return updated_html, extract_dir
    
    def run_debug(self, tour_id):
        """Run complete debug process"""
        print("=== DEBUG TRANSLATION PROCESS ===")
        result = self.step3_create_html(tour_id)
        if result:
            print("\n=== VERIFICATION FILES CREATED ===")
            print("1. Russian audio files: /tmp/russian_audio_*.mp3")
            print("2. Russian HTML file: /tmp/russian_index.html")
            print("\nPlease verify these files before proceeding to database storage.")

if __name__ == '__main__':
    debug = DebugTranslation()
    debug.run_debug(5)  # Chestnut Hill tour