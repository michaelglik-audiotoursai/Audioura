#!/usr/bin/env python3
"""
Translation Service - AudioTours Multi-Language Support
Port: 5030
"""

from flask import Flask, request, jsonify, make_response
import boto3
import zipfile
import io
import uuid
import psycopg2
import logging
from concurrent.futures import ThreadPoolExecutor
import os
import json
from bs4 import BeautifulSoup

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

class TranslationService:
    def __init__(self):
        self.translate_client = boto3.client('translate', region_name='us-east-1')
        self.polly_client = boto3.client('polly', region_name='us-east-1')
        self.executor = ThreadPoolExecutor(max_workers=5)
        
    def get_db_connection(self):
        return psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password123"
        )
    
    def translate_text(self, text, target_language):
        """Translate text using AWS Translate"""
        if target_language == 'en':
            return text
            
        try:
            response = self.translate_client.translate_text(
                Text=text[:5000],  # AWS limit
                SourceLanguageCode='en',
                TargetLanguageCode=target_language
            )
            return response['TranslatedText']
        except Exception as e:
            logging.error(f"Translation error: {e}")
            return text
    
    def generate_audio(self, text, target_language):
        """Generate audio using AWS Polly"""
        voice_map = {
            'en': 'Joanna',
            'es': 'Lucia',
            'fr': 'Celine', 
            'de': 'Marlene',
            'ru': 'Tatyana',
            'zh': 'Zhiyu'
        }
        
        try:
            response = self.polly_client.synthesize_speech(
                Text=text[:3000],  # AWS limit
                OutputFormat='mp3',
                VoiceId=voice_map.get(target_language, 'Joanna')
            )
            return response['AudioStream'].read()
        except Exception as e:
            logging.error(f"Audio generation error: {e}")
            return None
    
    def translate_tour_with_audio(self, original_tour_id, target_language):
        """Translate a tour with full audio generation preserving original HTML structure"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get original tour with tour_content
            cursor.execute(
                "SELECT id, tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language FROM audio_tours WHERE id = %s", 
                (original_tour_id,)
            )
            original_tour = cursor.fetchone()
            if not original_tour:
                logging.error(f"Original tour {original_tour_id} not found")
                return None
            
            tour_content = original_tour[7]  # tour_content column
            original_zip_data = original_tour[3]  # audio_tour column
            
            if not tour_content:
                logging.warning(f"No tour content found for tour {original_tour_id}, falling back to ZIP extraction")
                return self._translate_tour_from_zip(original_tour, target_language)
            
            logging.info(f"Using stored tour content: {len(tour_content)} characters")
            
            # Check if translation already exists
            cursor.execute(
                "SELECT id FROM audio_tours WHERE original_tour_id = %s AND content_language = %s",
                (original_tour_id, target_language)
            )
            existing = cursor.fetchone()
            if existing:
                logging.info(f"Translation already exists: {existing[0]}")
                return existing[0]
            
            # Translate tour name and request string
            translated_name = self.translate_text(original_tour[1], target_language)
            translated_request = self.translate_text(original_tour[2], target_language)
            
            # Split tour content into stops using the same logic as tour generation
            tour_stops = self._split_tour_content_into_stops(tour_content)
            logging.info(f"Split tour content into {len(tour_stops)} stops")
            
            # Translate each stop
            translated_stops = []
            for i, stop_text in enumerate(tour_stops):
                try:
                    translated_stop = self.translate_text(stop_text, target_language)
                    translated_stops.append(translated_stop)
                    logging.info(f"Translated stop {i+1}/{len(tour_stops)}")
                except Exception as e:
                    logging.error(f"Error translating stop {i+1}: {e}")
                    translated_stops.append(stop_text)  # Keep original on error
            
            # Generate audio for each translated stop
            translated_audio_files = []
            for i, translated_text in enumerate(translated_stops):
                try:
                    audio_bytes = self.generate_audio(translated_text, target_language)
                    if audio_bytes:
                        translated_audio_files.append(audio_bytes)
                        logging.info(f"Generated audio for stop {i+1}/{len(translated_stops)}")
                    else:
                        logging.warning(f"Failed to generate audio for stop {i+1}")
                        translated_audio_files.append(None)
                except Exception as e:
                    logging.error(f"Error generating audio for stop {i+1}: {e}")
                    translated_audio_files.append(None)
            
            # Create translated ZIP by preserving original HTML structure and replacing audio
            translated_zip_data = self._create_mobile_compatible_zip(
                original_zip_data, translated_name, translated_audio_files, target_language, translated_stops
            )
            
            # Store translated tour content for future reference
            translated_tour_content = "\n\n".join([
                f"Stop {i+1}: {stop}" for i, stop in enumerate(translated_stops)
            ])
            
            # Create new tour record
            cursor.execute("""
                INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, 
                                       lat, lng, content_language, original_tour_id, tour_content)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (
                translated_name, translated_request, translated_zip_data, original_tour[4],
                original_tour[5], original_tour[6], target_language, original_tour_id, translated_tour_content
            ))
            
            new_tour_id = cursor.fetchone()[0]
            conn.commit()
            
            logging.info(f"Created translated tour {new_tour_id} in {target_language} with {len(translated_stops)} stops")
            return new_tour_id
            
        except Exception as e:
            logging.error(f"Tour translation with audio error: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def translate_zip_audio(self, zip_data, target_language):
        """Translate audio content in ZIP file - extracts and replaces embedded base64 audio data"""
        import tempfile
        import os
        import re
        import base64
        from bs4 import BeautifulSoup
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract original ZIP
                zip_path = os.path.join(temp_dir, "original.zip")
                with open(zip_path, 'wb') as f:
                    f.write(zip_data)
                
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Find and process HTML file
                html_files = [f for f in os.listdir(extract_dir) if f.endswith('.html')]
                if not html_files:
                    return zip_data  # Return original if no HTML
                
                html_file = os.path.join(extract_dir, html_files[0])
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Parse HTML and find embedded audio data
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Find all base64 audio data URLs
                audio_pattern = r'data:audio/[^;]+;base64,([A-Za-z0-9+/=]+)'
                audio_matches = re.findall(audio_pattern, html_content)
                
                logging.info(f"Found {len(audio_matches)} embedded audio data URLs")
                
                # Extract text content for translation
                text_elements = []
                
                # Find paragraphs with substantial text
                paragraphs = soup.find_all('p')
                for p in paragraphs:
                    text = p.get_text().strip()
                    if text and len(text) > 10:
                        text_elements.append(text)
                
                # Find headings
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    headings = soup.find_all(tag)
                    for h in headings:
                        text = h.get_text().strip()
                        if text and len(text) > 5:
                            text_elements.append(text)
                
                # Find other text content in divs, spans, etc.
                for tag in ['div', 'span']:
                    elements = soup.find_all(tag)
                    for elem in elements:
                        # Only direct text, not nested
                        if elem.string and elem.string.strip() and len(elem.string.strip()) > 10:
                            text_elements.append(elem.string.strip())
                
                logging.info(f"Extracted {len(text_elements)} text elements for translation")
                
                # Generate translated audio for each text element
                translated_audio_data = []
                for i, text in enumerate(text_elements):
                    try:
                        # Translate text
                        translated_text = self.translate_text(text, target_language)
                        
                        # Generate audio using AWS Polly
                        audio_bytes = self.generate_audio(translated_text, target_language)
                        if audio_bytes:
                            # Encode as base64
                            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                            translated_audio_data.append(audio_base64)
                            logging.info(f"Generated translated audio {i+1}/{len(text_elements)} ({len(audio_base64)} chars)")
                        else:
                            # Keep original if translation fails
                            if i < len(audio_matches):
                                translated_audio_data.append(audio_matches[i])
                            logging.warning(f"Failed to generate audio for text element {i+1}")
                    except Exception as e:
                        # Keep original if translation fails
                        if i < len(audio_matches):
                            translated_audio_data.append(audio_matches[i])
                        logging.error(f"Error translating audio {i+1}: {e}")
                
                # Replace embedded audio data in HTML
                updated_html = html_content
                for i, (original_audio, translated_audio) in enumerate(zip(audio_matches, translated_audio_data)):
                    if original_audio != translated_audio:
                        # Replace the base64 data part only
                        original_data_url = f'data:audio/mp3;base64,{original_audio}'
                        translated_data_url = f'data:audio/mp3;base64,{translated_audio}'
                        updated_html = updated_html.replace(original_data_url, translated_data_url, 1)
                        logging.info(f"Replaced embedded audio data {i+1}")
                
                # Translate visible text content
                soup = BeautifulSoup(updated_html, 'html.parser')
                
                # Translate paragraphs
                for p in soup.find_all('p'):
                    if p.get_text().strip() and len(p.get_text().strip()) > 10:
                        original_text = p.get_text().strip()
                        translated_text = self.translate_text(original_text, target_language)
                        p.string = translated_text
                
                # Translate headings
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    for h in soup.find_all(tag):
                        if h.get_text().strip():
                            original_text = h.get_text().strip()
                            translated_text = self.translate_text(original_text, target_language)
                            h.string = translated_text
                
                # Update title
                title_tag = soup.find('title')
                if title_tag and title_tag.get_text().strip():
                    translated_title = self.translate_text(title_tag.get_text(), target_language)
                    title_tag.string = translated_title
                
                # Save updated HTML with translated audio
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(str(soup))
                
                # Create new ZIP with translated content
                new_zip_path = os.path.join(temp_dir, "translated.zip")
                with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                    for root, dirs, files in os.walk(extract_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, extract_dir)
                            zip_ref.write(file_path, arc_name)
                
                # Read translated ZIP data
                with open(new_zip_path, 'rb') as f:
                    translated_zip = f.read()
                
                logging.info(f"Successfully translated ZIP with {len(audio_matches)} embedded audio files")
                return translated_zip
                    
        except Exception as e:
            logging.error(f"ZIP audio translation error: {e}")
            return zip_data  # Return original on error
    def _split_tour_content_into_stops(self, tour_content):
        """Split tour content into individual stops using the same logic as tour generation"""
        import re
        
        # Split content by stops using regex pattern
        stops = re.split(r'\n\s*Stop\s+(\d+):', tour_content)
        
        text_content = []
        
        if len(stops) > 1:
            stops = stops[1:]  # Remove title part
            
            # Process stops in pairs (number, content)
            for i in range(0, len(stops), 2):
                if i + 1 < len(stops):
                    stop_num = stops[i].strip()
                    stop_content = stops[i+1].strip()
                    
                    # Clean up the content
                    if stop_content:
                        text_content.append(stop_content)
        
        # If no stops found, try alternative splitting
        if not text_content:
            # Try splitting by numbered sections
            lines = tour_content.split('\n')
            current_stop = []
            
            for line in lines:
                line = line.strip()
                if re.match(r'^\d+\.', line) or re.match(r'^Stop \d+', line):
                    if current_stop:
                        text_content.append('\n'.join(current_stop))
                        current_stop = []
                    current_stop.append(line)
                elif line and current_stop:
                    current_stop.append(line)
            
            # Add the last stop
            if current_stop:
                text_content.append('\n'.join(current_stop))
        
        # If still no content, use the entire text as one stop
        if not text_content and tour_content.strip():
            text_content = [tour_content.strip()]
        
        return text_content
    
    def _create_mobile_compatible_zip(self, original_zip_data, translated_name, audio_files, target_language, translated_stops):
        """Create mobile-compatible ZIP by preserving original HTML structure and replacing audio"""
        import tempfile
        import os
        import base64
        import re
        from bs4 import BeautifulSoup
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract original ZIP
                original_zip_path = os.path.join(temp_dir, "original.zip")
                with open(original_zip_path, 'wb') as f:
                    f.write(original_zip_data)
                
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir)
                
                with zipfile.ZipFile(original_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Find and process HTML file
                html_files = [f for f in os.listdir(extract_dir) if f.endswith('.html')]
                if not html_files:
                    logging.error("No HTML file found in original ZIP")
                    return original_zip_data
                
                html_file_path = os.path.join(extract_dir, html_files[0])
                with open(html_file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Parse HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Update title with translated name
                title_tag = soup.find('title')
                if title_tag:
                    title_tag.string = translated_name
                
                # Find all base64 audio data URLs in the HTML - try multiple patterns
                audio_patterns = [
                    r'data:audio/[^;]+;base64,([A-Za-z0-9+/=]+)',  # Standard pattern
                    r'data:audio/mp3;base64,([A-Za-z0-9+/=]+)',     # MP3 specific
                    r'data:audio/mpeg;base64,([A-Za-z0-9+/=]+)',    # MPEG specific
                    r'src="data:audio/[^"]+;base64,([A-Za-z0-9+/=]+)"'  # With src attribute
                ]
                
                audio_matches = []
                for pattern in audio_patterns:
                    matches = re.findall(pattern, html_content)
                    if matches:
                        audio_matches.extend(matches)
                        logging.info(f"Found {len(matches)} audio URLs with pattern: {pattern[:30]}...")
                
                # Remove duplicates while preserving order
                seen = set()
                unique_audio_matches = []
                for match in audio_matches:
                    if match not in seen:
                        seen.add(match)
                        unique_audio_matches.append(match)
                
                audio_matches = unique_audio_matches
                
                logging.info(f"Found {len(audio_matches)} embedded audio data URLs")
                logging.info(f"Have {len(audio_files)} translated audio files")
                
                # Replace embedded audio data with translated audio
                updated_html = str(soup)
                
                # If no embedded audio found, try to find audio elements and add Russian audio
                if not audio_matches and audio_files:
                    logging.info("No embedded audio found, looking for audio elements to replace")
                    
                    # Find audio elements in the HTML
                    audio_elements = soup.find_all('audio')
                    logging.info(f"Found {len(audio_elements)} audio elements")
                    
                    # Replace audio elements with Russian audio
                    for i, (audio_elem, translated_audio_bytes) in enumerate(zip(audio_elements, audio_files)):
                        if translated_audio_bytes:
                            try:
                                # Encode translated audio as base64
                                translated_audio_b64 = base64.b64encode(translated_audio_bytes).decode('utf-8')
                                translated_data_url = f'data:audio/mp3;base64,{translated_audio_b64}'
                                
                                # Find or create source element
                                source_elem = audio_elem.find('source')
                                if source_elem:
                                    source_elem['src'] = translated_data_url
                                else:
                                    # Create new source element
                                    new_source = soup.new_tag('source', src=translated_data_url, type='audio/mpeg')
                                    audio_elem.insert(0, new_source)
                                
                                logging.info(f"Replaced audio element {i+1} with Russian audio")
                                
                            except Exception as e:
                                logging.error(f"Error replacing audio element {i+1}: {e}")
                    
                    updated_html = str(soup)
                    
                    # Translate visible text content in HTML
                    soup = BeautifulSoup(updated_html, 'html.parser')
                    
                    logging.info("Starting HTML text translation")
                    
                    # Translate all text content that should be in Russian
                    translated_count = 0
                    for p in soup.find_all('p'):
                        if p.get_text().strip() and len(p.get_text().strip()) > 5:
                            original_text = p.get_text().strip()
                            translated_text = self.translate_text(original_text, target_language)
                            p.string = translated_text
                            translated_count += 1
                            logging.info(f"Translated paragraph {translated_count}: {original_text[:50]}... -> {translated_text[:50]}...")
                    
                    for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        for h in soup.find_all(tag):
                            if h.get_text().strip():
                                original_text = h.get_text().strip()
                                translated_text = self.translate_text(original_text, target_language)
                                h.string = translated_text
                                translated_count += 1
                                logging.info(f"Translated heading: {original_text} -> {translated_text}")
                    
                    logging.info(f"Completed HTML text translation: {translated_count} elements translated")
                    updated_html = str(soup)
                    
                else:
                    # Original method for embedded base64 audio
                    for i, (original_audio_b64, translated_audio_bytes) in enumerate(zip(audio_matches, audio_files)):
                        if translated_audio_bytes:
                            try:
                                # Encode translated audio as base64
                                translated_audio_b64 = base64.b64encode(translated_audio_bytes).decode('utf-8')
                                
                                # Replace the base64 data in the HTML
                                original_data_url = f'data:audio/mp3;base64,{original_audio_b64}'
                                translated_data_url = f'data:audio/mp3;base64,{translated_audio_b64}'
                                
                                updated_html = updated_html.replace(original_data_url, translated_data_url, 1)
                                logging.info(f"Replaced embedded audio data {i+1}/{len(audio_matches)}")
                                
                            except Exception as e:
                                logging.error(f"Error replacing audio {i+1}: {e}")
                        else:
                            logging.warning(f"No translated audio available for stop {i+1}, keeping original")
                
                # Save updated HTML
                with open(html_file_path, 'w', encoding='utf-8') as f:
                    f.write(updated_html)
                
                # Update manifest.json if it exists
                manifest_path = os.path.join(extract_dir, 'manifest.json')
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest = json.load(f)
                        
                        manifest['name'] = translated_name
                        manifest['short_name'] = translated_name[:12]
                        
                        with open(manifest_path, 'w', encoding='utf-8') as f:
                            json.dump(manifest, f, indent=2)
                        
                        logging.info("Updated manifest.json with translated name")
                    except Exception as e:
                        logging.warning(f"Could not update manifest.json: {e}")
                
                # Add translated tour content as text file for reference
                if audio_files:
                    # Create full Russian tour content file
                    tour_content_text = "\n\n".join([
                        f"Stop {i+1}: {stop}" for i, stop in enumerate(translated_stops)
                    ])
                    content_file = os.path.join(extract_dir, 'tour_content.txt')
                    with open(content_file, 'w', encoding='utf-8') as f:
                        f.write(tour_content_text)
                    
                    # Create individual Russian stop files
                    for i, translated_stop in enumerate(translated_stops):
                        stop_file = os.path.join(extract_dir, f'audio_{i}.txt')
                        with open(stop_file, 'w', encoding='utf-8') as f:
                            f.write(translated_stop)
                
                # Create new ZIP with translated content
                new_zip_path = os.path.join(temp_dir, "translated.zip")
                with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(extract_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, extract_dir)
                            zipf.write(file_path, arc_name)
                
                # Read translated ZIP data
                with open(new_zip_path, 'rb') as f:
                    translated_zip = f.read()
                
                logging.info(f"Created mobile-compatible translated ZIP ({len(translated_zip)} bytes)")
                return translated_zip
                
        except Exception as e:
            logging.error(f"Error creating mobile-compatible ZIP: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return original_zip_data  # Return original on error
    
    def _generate_translated_html(self, tour_name, translated_stops, audio_files, target_language):
        """Generate HTML with embedded translated audio data"""
        import base64
        
        html = f'''<!DOCTYPE html>
<html lang="{target_language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{tour_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .tour-header {{ text-align: center; margin-bottom: 30px; }}
        .audio-item {{ margin: 20px 0; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stop-title {{ color: #2c3e50; margin-bottom: 10px; }}
        .stop-content {{ margin: 15px 0; line-height: 1.6; }}
        audio {{ width: 100%; margin-top: 10px; }}
        .language-indicator {{ background: #3498db; color: white; padding: 5px 10px; border-radius: 15px; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="tour-header">
        <h1>{tour_name}</h1>
        <span class="language-indicator">{target_language.upper()}</span>
    </div>'''
        
        for i, (stop_text, audio_data) in enumerate(zip(translated_stops, audio_files)):
            # Extract stop title from text content
            lines = stop_text.split('\n')
            stop_title = lines[0].strip() if lines else f"Stop {i+1}"
            
            # Create audio data URL if audio is available
            audio_element = ""
            if audio_data:
                try:
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    audio_data_url = f'data:audio/mp3;base64,{audio_base64}'
                    audio_element = f'''
        <audio id="audio{i}" controls preload="metadata">
            <source src="{audio_data_url}" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>'''
                except Exception as e:
                    logging.error(f"Error encoding audio for stop {i+1}: {e}")
                    audio_element = f'<p><em>Audio not available for this stop</em></p>'
            else:
                audio_element = f'<p><em>Audio generation failed for this stop</em></p>'
            
            html += f'''
    <div class="audio-item">
        <h3 class="stop-title">{stop_title}</h3>
        <div class="stop-content">
            <p>{stop_text.replace(chr(10), '</p><p>')}</p>
        </div>{audio_element}
    </div>'''
        
        # Add voice control JavaScript
        html += '''
    
    <script>
        let audioElements = [];
        let currentStopIndex = 0;
        
        window.playAudio = function() {
            audioElements.forEach((audio, index) => {
                if (index !== currentStopIndex) {
                    audio.pause();
                    audio.currentTime = 0;
                }
            });
            
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].play();
                return "Success: Playing stop-" + currentStopIndex;
            }
            return "Error: No audio to play";
        };
        
        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return "Success: Audio paused";
            }
            return "Error: No audio to pause";
        };
        
        window.nextStop = function() {
            if (currentStopIndex < audioElements.length - 1) {
                currentStopIndex++;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at last stop";
        };
        
        window.previousStop = function() {
            if (currentStopIndex > 0) {
                currentStopIndex--;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at first stop";
        };
        
        document.addEventListener('DOMContentLoaded', function() {
            const audios = document.querySelectorAll('audio');
            audioElements = Array.from(audios);
            
            audioElements.forEach((audio, index) => {
                audio.addEventListener('play', function() {
                    currentStopIndex = index;
                });
            });
        });
    </script>
</body>
</html>'''
        return html
    
    def _translate_tour_from_zip(self, original_tour, target_language):
        """Fallback method for tours without stored content - uses old ZIP extraction method"""
        logging.info("Using fallback ZIP extraction method for tour translation")
        
        # Translate tour name and request string
        translated_name = self.translate_text(original_tour[1], target_language)
        translated_request = self.translate_text(original_tour[2], target_language)
        
        # Process ZIP file for audio translation
        original_zip_data = original_tour[3]  # audio_tour column
        translated_zip_data = self.translate_zip_audio(original_zip_data, target_language)
        
        # Create new tour record
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, 
                                       lat, lng, content_language, original_tour_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (
                translated_name, translated_request, translated_zip_data, original_tour[4],
                original_tour[5], original_tour[6], target_language, original_tour[0]
            ))
            
            new_tour_id = cursor.fetchone()[0]
            conn.commit()
            
            logging.info(f"Created translated tour {new_tour_id} in {target_language} using ZIP fallback")
            return new_tour_id
            
        except Exception as e:
            logging.error(f"Fallback tour translation error: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

# Initialize translation service
translation_service = TranslationService()

def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.after_request
def after_request(response):
    return add_cors_headers(response)

@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    if request.method == 'OPTIONS':
        return make_response()
    return jsonify({"status": "healthy", "service": "translation"})

@app.route('/translate-with-audio', methods=['POST', 'OPTIONS'])
def translate_content_with_audio():
    if request.method == 'OPTIONS':
        return make_response()
    
    data = request.json
    content_id = data.get('content_id')
    content_type = data.get('content_type')  # 'tour' or 'article'
    languages = data.get('languages', ['en'])
    
    results = {}
    for lang in languages:
        if lang == 'en':
            results[lang] = {'status': 'original', 'id': content_id}
            continue
            
        if content_type == 'tour':
            translated_id = translation_service.translate_tour_with_audio(content_id, lang)
        else:
            translated_id = translation_service.translate_article(content_id, lang)
        
        if translated_id:
            results[lang] = {'status': 'translated', 'id': translated_id}
        else:
            results[lang] = {'status': 'failed', 'id': None}
    
    return jsonify({
        'status': 'completed',
        'translations': results
    })
def translate_content():
    if request.method == 'OPTIONS':
        return make_response()
    
    data = request.json
    content_id = data.get('content_id')
    content_type = data.get('content_type')  # 'tour' or 'article'
    languages = data.get('languages', ['en'])
    
    results = {}
    for lang in languages:
        if lang == 'en':
            results[lang] = {'status': 'original', 'id': content_id}
            continue
            
        if content_type == 'tour':
            translated_id = translation_service.translate_tour(content_id, lang)
        else:
            translated_id = translation_service.translate_article(content_id, lang)
        
        if translated_id:
            results[lang] = {'status': 'translated', 'id': translated_id}
        else:
            results[lang] = {'status': 'failed', 'id': None}
    
    return jsonify({
        'status': 'completed',
        'translations': results
    })

@app.route('/supported-languages', methods=['GET', 'OPTIONS'])
def get_supported_languages():
    if request.method == 'OPTIONS':
        return make_response()
    
    conn = translation_service.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM supported_languages WHERE enabled = TRUE ORDER BY language_code")
        languages = cursor.fetchall()
        
        result = []
        for lang in languages:
            result.append({
                'code': lang[0],
                'name': lang[1],
                'voice': lang[2],
                'enabled': lang[3]
            })
        
        return jsonify({'languages': result})
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5030, debug=True)