#!/usr/bin/env python3
"""
Translation Service - AudioTours Multi-Language Support
Port: 5030
"""

from flask import Flask, request, jsonify, make_response
import boto3
import zipfile
import io
import re
import uuid
import psycopg2
import logging
from concurrent.futures import ThreadPoolExecutor
import os
import json
from bs4 import BeautifulSoup, NavigableString

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

class TranslationService:
    def __init__(self):
        self.translate_client = boto3.client('translate', region_name='us-east-1')
        self.polly_client = boto3.client('polly', region_name='us-east-1')
        self.executor = ThreadPoolExecutor(max_workers=5)
        
    def get_db_connection(self):
        return psycopg2.connect(
            host=os.getenv('DB_HOST', 'development-postgres-2-1'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
    
    # Only these two labels must stay in English — mobile app parses them by exact string match.
    # All other labels (Type/Specialty, Orientation, etc.) should be translated normally.
    _METADATA_LABELS = ['Coordinates', 'Address']

    # Compiled pattern for stripping translated metadata label lines from .txt body.
    # Matches any line whose first word(s) correspond to a _METADATA_LABELS key followed
    # by any non-word separator (covers ASCII ':', full-width '\uff1a', French '\xa0:', etc.)
    _TRANSLATED_LABEL_RE = re.compile(
        r'^\s*\S+\W.*$',  # placeholder — built dynamically per-label in _restore_metadata_labels
        re.IGNORECASE
    )

    def _restore_metadata_labels(self, original_text, translated_text, target_language):
        """Prepend original English Coordinates/Address lines to the top of the translated stop.
        Mobile app parses these fields by exact English string match to place map pins.
        Prepending is language-agnostic: no regex on translated text, works for any language
        including RTL scripts (Arabic, Hebrew) and any future AWS Translate separator variants
        (e.g. French non-breaking space \xa0 before colon). Saves 2 AWS Translate calls per stop.
        The translated label lines (e.g. Coordonnees\xa0:) are stripped from the body so the
        .txt file does not contain duplicate coordinate entries."""
        if target_language == 'en':
            return translated_text
        english_lines = []
        for label in self._METADATA_LABELS:
            m = re.search(
                rf'^({re.escape(label)}\s*:.*)$',
                original_text, re.IGNORECASE | re.MULTILINE
            )
            if m:
                english_lines.append(m.group(1).strip())
        if not english_lines:
            return translated_text
        # Strip translated equivalents from body to avoid duplicate entries.
        # We match lines that start with the same word-count prefix as the English label
        # followed by any non-word separator — covers all known AWS Translate variants.
        body_lines = translated_text.split('\n')
        label_word_counts = [len(label.split()) for label in self._METADATA_LABELS]
        def _is_translated_metadata(line):
            stripped = line.strip()
            for wc in label_word_counts:
                words = stripped.split()
                if len(words) > wc:
                    prefix = ' '.join(words[:wc])
                    remainder = stripped[len(prefix):].lstrip()
                    if remainder and not remainder[0].isalnum():
                        # Check the English label is NOT present (don't strip the prepended lines)
                        if not any(
                            re.match(rf'^{re.escape(lbl)}\s*:', stripped, re.IGNORECASE)
                            for lbl in self._METADATA_LABELS
                        ):
                            return True
            return False
        clean_body = [l for l in body_lines if not _is_translated_metadata(l)]
        # Prepend English lines at the very top — unconditionally first, no dependency on line order
        return '\n'.join(english_lines + clean_body)

    def translate_text(self, text, target_language, preserve_voice_commands=False):
        """Translate text using AWS Translate with optional voice command preservation"""
        if target_language == 'en':
            return text
            
        try:
            response = self.translate_client.translate_text(
                Text=text[:5000],  # AWS limit
                SourceLanguageCode='en',
                TargetLanguageCode=target_language
            )
            translated_text = response['TranslatedText']
            
            # Preserve English voice commands if requested
            if preserve_voice_commands:
                translated_text = self._preserve_voice_commands(text, translated_text, target_language)
            
            return translated_text
        except Exception as e:
            logging.error(f"Translation error: {e}")
            return text
    
    def _preserve_voice_commands(self, original_text, translated_text, target_language='ru'):
        """Preserve English voice commands in translated text"""
        # Voice commands that must stay in English
        voice_commands = [
            "Play", "Pause", "Next topic", "Previous topic", "Repeat",
            "Forward 10 seconds", "Backward 5 seconds", "Play topic",
            "Play summary", "Play full article", "List major topics",
            "Next article", "Previous article", "What are my options"
        ]
        
        # Preserve voice command phrases
        for command in voice_commands:
            if command in original_text:
                # Find translated version and replace back to English
                try:
                    translated_command = self.translate_client.translate_text(
                        Text=command,
                        SourceLanguageCode='en',
                        TargetLanguageCode=target_language
                    )['TranslatedText']
                    translated_text = translated_text.replace(translated_command, command)
                except:
                    pass  # Keep original if translation fails
        
        return translated_text
    
    def generate_audio(self, text, target_language):
        """Generate audio using AWS Polly"""
        voice_map = {
            'en': 'Joanna',
            'es': 'Lucia',
            'fr': 'Celine', 
            'de': 'Marlene',
            'ru': 'Tatyana',
            'zh': 'Zhiyu',
            'ko': 'Seoyeon'
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
                "SELECT id, tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language, tour_blob_uri FROM audio_tours WHERE id = %s", 
                (original_tour_id,)
            )
            original_tour = cursor.fetchone()
            if not original_tour:
                logging.error(f"Original tour {original_tour_id} not found")
                return None
            
            tour_content = original_tour[7]  # tour_content column
            original_zip_data = original_tour[3]  # audio_tour column
            tour_blob_uri = original_tour[9] if len(original_tour) > 9 else None  # R2 blob key
            
            # If audio_tour is NULL but tour_blob_uri exists, download from R2
            if not original_zip_data and tour_blob_uri:
                logging.info(f"Tour {original_tour_id}: audio_tour is NULL, fetching from R2 blob: {tour_blob_uri}")
                try:
                    import boto3
                    r2_endpoint = os.getenv('R2_ENDPOINT', '')
                    r2_access_key = os.getenv('R2_ACCESS_KEY_ID', '')
                    r2_secret_key = os.getenv('R2_SECRET_ACCESS_KEY', '')
                    r2_bucket = os.getenv('R2_BUCKET', 'v1-audiotours-r2-bucket')
                    
                    if r2_endpoint and r2_access_key:
                        s3 = boto3.client('s3',
                            endpoint_url=r2_endpoint,
                            aws_access_key_id=r2_access_key,
                            aws_secret_access_key=r2_secret_key
                        )
                        response = s3.get_object(Bucket=r2_bucket, Key=tour_blob_uri)
                        original_zip_data = response['Body'].read()
                        logging.info(f"Downloaded {len(original_zip_data)} bytes from R2 for tour {original_tour_id}")
                    else:
                        logging.error(f"R2 credentials not configured — cannot fetch tour {original_tour_id} blob")
                except Exception as r2_err:
                    logging.error(f"Failed to download tour {original_tour_id} from R2: {r2_err}")
            
            if not tour_content:
                logging.warning(f"No tour content found for tour {original_tour_id}, falling back to ZIP extraction")
                # Verify ZIP has actual audio before attempting fallback
                if not original_zip_data:
                    logging.error(f"Tour {original_tour_id} has no tour_content AND no ZIP data — cannot translate")
                    return None
                try:
                    import io as _io
                    zip_bytes = original_zip_data.tobytes() if hasattr(original_zip_data, 'tobytes') else bytes(original_zip_data)
                    with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as _z:
                        audio_files_in_zip = [n for n in _z.namelist() if n.startswith('audio_') and n.endswith('.mp3')]
                    if not audio_files_in_zip:
                        logging.error(f"Tour {original_tour_id} ZIP has no audio files and no tour_content — cannot translate")
                        return None
                except Exception:
                    pass
                return self._translate_tour_from_zip(original_tour, target_language, zip_data_override=original_zip_data)
            
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
            
            # Translate each stop, then restore English metadata labels
            translated_stops = []
            tts_texts = []  # nav-stripped English text translated separately for audio
            for i, stop_text in enumerate(tour_stops):
                try:
                    translated_stop = self.translate_text(stop_text, target_language)
                    translated_stop = self._restore_metadata_labels(stop_text, translated_stop, target_language)
                    translated_stops.append(translated_stop)
                    # Strip nav fields in English BEFORE translating for TTS
                    tts_text = self.translate_text(self._strip_nav_fields_for_tts(stop_text), target_language)
                    tts_texts.append(tts_text)
                    logging.info(f"Translated stop {i+1}/{len(tour_stops)}")
                except Exception as e:
                    logging.error(f"Error translating stop {i+1}: {e}")
                    translated_stops.append(stop_text)  # Keep original on error
                    tts_texts.append(stop_text)
            
            # Generate audio for each translated stop
            translated_audio_files = []
            for i, translated_text in enumerate(tts_texts):
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
        """Translate audio content in ZIP file - handles both embedded base64 and modernized (separate mp3) formats"""
        import tempfile
        import os
        import base64
        
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
                
                # Detect modernized ZIP format: separate audio_N.mp3 files
                existing_mp3s = sorted([f for f in os.listdir(extract_dir) if re.match(r'audio_\d+\.mp3', f)])
                is_modernized_format = len(existing_mp3s) > 0
                
                if is_modernized_format and not audio_matches:
                    # === MODERNIZED FORMAT: separate mp3 files ===
                    logging.info(f"Modernized ZIP format detected ({len(existing_mp3s)} mp3 files). Translating and replacing audio.")
                    
                    # For each audio_N.mp3, source the text from its sibling audio_N.txt
                    # (the exact narration script that produced the original mp3).
                    # Fall back to HTML paragraph extraction only if .txt is missing.
                    html_fallback_texts = None  # lazy-loaded if needed
                    
                    for i, mp3_filename in enumerate(existing_mp3s, start=1):
                        mp3_path = os.path.join(extract_dir, mp3_filename)
                        txt_path = os.path.join(extract_dir, f'audio_{i}.txt')
                        
                        # Determine source text for this stop
                        if os.path.exists(txt_path):
                            with open(txt_path, 'r', encoding='utf-8') as f:
                                source_text = f.read().strip()
                            logging.info(f"Stop {i}: sourced from audio_{i}.txt ({len(source_text)} chars)")
                        else:
                            # Fallback: extract from HTML paragraphs (imprecise, last resort)
                            if html_fallback_texts is None:
                                html_fallback_texts = []
                                for p in soup.find_all('p'):
                                    text = p.get_text().strip()
                                    if text and len(text) > 10:
                                        html_fallback_texts.append(text)
                                logging.warning(f"audio_{i}.txt missing — falling back to HTML paragraphs ({len(html_fallback_texts)} elements)")
                            
                            idx = i - 1
                            if idx < len(html_fallback_texts):
                                source_text = html_fallback_texts[idx]
                            else:
                                logging.warning(f"No text source for stop {i}, keeping original {mp3_filename}")
                                continue
                        
                        if not source_text:
                            logging.warning(f"Empty text for stop {i}, keeping original {mp3_filename}")
                            continue
                        
                        try:
                            translated_text = self.translate_text(source_text, target_language)
                            # Restore English Coordinates/Address lines so mobile app can parse map pins
                            translated_text_with_meta = self._restore_metadata_labels(source_text, translated_text, target_language)
                            # For TTS audio: strip nav/metadata fields (don't read coordinates aloud)
                            tts_source = self._strip_nav_fields_for_tts(source_text)
                            tts_translated = self.translate_text(tts_source, target_language)
                            audio_bytes = self.generate_audio(tts_translated, target_language)
                            if audio_bytes:
                                with open(mp3_path, 'wb') as f:
                                    f.write(audio_bytes)
                                logging.info(f"Replaced {mp3_filename} with translated audio ({len(audio_bytes)} bytes)")
                                # Also write translated script (with metadata) back to audio_N.txt
                                with open(txt_path, 'w', encoding='utf-8') as f:
                                    f.write(translated_text_with_meta)
                            else:
                                logging.warning(f"Polly returned no audio for stop {i}, keeping original {mp3_filename}")
                        except Exception as e:
                            logging.error(f"Error translating audio for stop {i}: {e}")
                    
                    # Translate visible HTML text content
                    for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        for h in soup.find_all(tag):
                            text = h.get_text().strip()
                            if text:
                                translated_text = self.translate_text(text, target_language)
                                h.clear()
                                h.append(NavigableString(translated_text))
                    
                    for p in soup.find_all('p'):
                        text = p.get_text().strip()
                        if text and len(text) > 5:
                            translated_text = self.translate_text(text, target_language)
                            p.clear()
                            p.append(NavigableString(translated_text))
                    
                    # Update title
                    title_tag = soup.find('title')
                    if title_tag and title_tag.get_text().strip():
                        translated_title = self.translate_text(title_tag.get_text(), target_language)
                        title_tag.string = translated_title
                    
                    # Save updated HTML
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(str(soup))
                    
                    # Update manifest.json with translated name
                    manifest_path = os.path.join(extract_dir, 'manifest.json')
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest = json.load(f)
                            original_name = manifest.get('name', '')
                            if original_name:
                                translated_manifest_name = self.translate_text(original_name, target_language)
                                manifest['name'] = translated_manifest_name
                                manifest['short_name'] = translated_manifest_name[:12]
                            with open(manifest_path, 'w', encoding='utf-8') as f:
                                json.dump(manifest, f, indent=2, ensure_ascii=False)
                            logging.info(f"Updated manifest.json with translated name")
                        except Exception as e:
                            logging.warning(f"Could not update manifest.json: {e}")
                    
                    # Create new ZIP with translated content
                    new_zip_path = os.path.join(temp_dir, "translated.zip")
                    with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                        for root, dirs, files in os.walk(extract_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arc_name = os.path.relpath(file_path, extract_dir)
                                zip_ref.write(file_path, arc_name)
                    
                    with open(new_zip_path, 'rb') as f:
                        translated_zip = f.read()
                    
                    logging.info(f"Successfully translated modernized ZIP with {len(existing_mp3s)} mp3 files replaced")
                    return translated_zip
                
                # === LEGACY FORMAT: embedded base64 audio ===
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
            return original_zip_data  # Return original on error
    
    def translate_article(self, original_article_id, target_language):
        """Translate a newsletter article with audio generation matching English structure"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get original article with major_points
            cursor.execute(
                "SELECT article_id, article_text, request_string, url, article_type, created_at, major_points FROM article_requests WHERE article_id = %s", 
                (original_article_id,)
            )
            original_article = cursor.fetchone()
            if not original_article:
                logging.error(f"Original article {original_article_id} not found")
                return None
            
            article_text = original_article[1]  # article_text column
            major_points = original_article[6]  # major_points column
            
            # Convert memoryview to string if needed
            if isinstance(article_text, memoryview):
                article_text = article_text.tobytes().decode('utf-8')
            elif isinstance(article_text, bytes):
                article_text = article_text.decode('utf-8')
            
            if not article_text or len(article_text.strip()) < 50:
                logging.error(f"Article {original_article_id} has insufficient content for translation")
                return None
            
            logging.info(f"Translating article with {len(article_text)} characters")
            
            # Check if translation already exists
            cursor.execute(
                "SELECT article_id FROM article_requests WHERE original_article_id = %s AND content_language = %s",
                (original_article_id, target_language)
            )
            existing = cursor.fetchone()
            if existing:
                logging.info(f"Translation already exists: {existing[0]}")
                return existing[0]
            
            # Parse major points if available
            topics = []
            if major_points:
                try:
                    if isinstance(major_points, list):
                        topics = major_points
                    else:
                        topics = json.loads(major_points)
                    logging.info(f"Found {len(topics)} topics for translation")
                except Exception as e:
                    logging.error(f"Failed to parse major_points: {e}")
                    topics = []
            
            # Translate article content and title
            translated_title = self.translate_text(original_article[2], target_language)  # request_string (title)
            translated_content = self.translate_text(article_text, target_language)
            
            # Translate each topic
            translated_topics = []
            for i, topic in enumerate(topics):
                try:
                    translated_topic = {
                        'summary': self.translate_text(topic.get('summary', ''), target_language),
                        'audio_text': self.translate_text(topic.get('audio_text', ''), target_language),
                        'segment_id': topic.get('segment_id', i),
                        'short_title': self.translate_text(topic.get('short_title', f'Topic {i+1}'), target_language)
                    }
                    translated_topics.append(translated_topic)
                    logging.info(f"Translated topic {i+1}: {translated_topic['short_title']}")
                except Exception as e:
                    logging.error(f"Error translating topic {i+1}: {e}")
                    translated_topics.append(topic)  # Keep original on error
            
            # Create mobile-compatible ZIP matching English structure exactly
            translated_zip_data = self._create_english_structure_zip(
                translated_title, translated_content, translated_topics, target_language
            )
            
            # Generate new article ID
            new_article_id = str(uuid.uuid4())
            
            # Store translated article in article_requests table
            if original_article[3]:  # If original URL exists
                translated_url = f"{original_article[3]}?lang={target_language}"
            else:
                # Generate unique URL if original is None
                translated_url = f"translated-article-{new_article_id}?lang={target_language}"
            
            cursor.execute("""
                INSERT INTO article_requests (article_id, article_text, request_string, url, 
                                            article_type, status, created_at, 
                                            content_language, original_article_id, major_points)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                new_article_id, translated_content, translated_title, translated_url,
                original_article[4], 'finished', original_article[5],
                target_language, original_article_id, json.dumps(translated_topics)
            ))
            
            # Store in news_audios table for download
            cursor.execute("""
                INSERT INTO news_audios (article_id, article_name, news_article, number_requested, article_type)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                new_article_id, translated_title, translated_zip_data, 1, original_article[4] or 'Others'
            ))
            
            conn.commit()
            
            logging.info(f"Created translated article {new_article_id} in {target_language} with {len(translated_topics)} topics")
            return new_article_id
            
        except Exception as e:
            logging.error(f"Article translation error: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def _create_english_structure_zip(self, title, content, topics, target_language):
        """Create ZIP matching exact English article structure with multiple MP3 files"""
        import tempfile
        import os
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_files = []
                
                # Split content into summary and full text (matching English format)
                parts = content.split('\n\nFull Article:', 1)
                if len(parts) == 2:
                    summary_text = parts[0].replace('Summary: ', '')
                    full_text = parts[1]  # Only the full article part
                else:
                    # If no "Full Article:" marker, create proper separation
                    sentences = content.split('. ')
                    if len(sentences) > 3:
                        summary_text = '. '.join(sentences[:2]) + '.'
                        full_text = '. '.join(sentences[2:])  # Remaining content as full article
                    else:
                        summary_text = content[:200] + '...'
                        full_text = content  # Use full content if too short to split
                
                # Generate summary audio (audio_1.mp3)
                summary_audio = self.generate_audio(f"Article Summary: {summary_text}", target_language)
                if summary_audio:
                    summary_file = os.path.join(temp_dir, 'audio_1.mp3')
                    with open(summary_file, 'wb') as f:
                        f.write(summary_audio)
                    audio_files.append(('audio_1.mp3', 'Summary'))
                
                # Generate topic audios (audio-1.mp3, audio-2.mp3, etc.)
                for i, topic in enumerate(topics):
                    try:
                        topic_text = topic.get('audio_text', topic.get('summary', f'Topic {i+1}'))
                        topic_audio = self.generate_audio(topic_text, target_language)
                        if topic_audio:
                            segment_id = topic.get('segment_id', i)
                            audio_filename = f'audio-{segment_id + 1}.mp3'
                            audio_path = os.path.join(temp_dir, audio_filename)
                            with open(audio_path, 'wb') as f:
                                f.write(topic_audio)
                            audio_files.append((audio_filename, topic.get('short_title', f'Topic {i+1}')))
                            logging.info(f"Generated {audio_filename} for topic: {topic.get('short_title', f'Topic {i+1}')}")
                    except Exception as e:
                        logging.error(f"Error generating audio for topic {i+1}: {e}")
                
                # Generate topics list audio (audio-topics.mp3) - KEEP VOICE COMMANDS IN ENGLISH
                if topics:
                    topics_text = "Here are the major topics covered in this article: "
                    for i, topic in enumerate(topics, 1):
                        short_title = topic.get('short_title', f'Topic {i}')
                        topics_text += f"{short_title}. "
                    topics_text += "You can ask me to play any of these topics by saying 'Play topic' followed by the number."
                    
                    # Translate topics text but preserve voice commands
                    translated_topics_text = self.translate_text(topics_text, target_language, preserve_voice_commands=True)
                    topics_audio = self.generate_audio(translated_topics_text, target_language)
                    if topics_audio:
                        topics_file = os.path.join(temp_dir, 'audio-topics.mp3')
                        with open(topics_file, 'wb') as f:
                            f.write(topics_audio)
                        audio_files.append(('audio-topics.mp3', 'Topics List'))
                
                # Generate help audio (audio-help.mp3) - KEEP COMPLETELY IN ENGLISH
                help_text = """Here are the voice commands you can use: 
                Say 'Play' to start or resume audio. Say 'Pause' to stop audio. 
                Say 'Next topic' or 'Previous topic' to navigate between sections. 
                Say 'Forward 10 seconds' or 'Backward 5 seconds' to skip within audio. 
                Say 'Repeat' to restart current audio from beginning. 
                Say 'Play topic' followed by a number or topic name to jump to specific sections. 
                Say 'Play summary' for article summary or 'Play full article' for complete text. 
                Say 'List major topics' to hear all available sections. 
                Say 'Next article' or 'Previous article' to switch between articles. 
                You can also say 'What are my options' anytime to hear this help again."""
                
                # Keep help text completely in English for mobile app compatibility
                help_audio = self.generate_audio(help_text, target_language)
                if help_audio:
                    help_file = os.path.join(temp_dir, 'audio-help.mp3')
                    with open(help_file, 'wb') as f:
                        f.write(help_audio)
                    audio_files.append(('audio-help.mp3', 'Help Commands'))
                
                # Generate full article audio (audio-99.mp3) - ONLY full article, not summary
                full_audio = self.generate_audio(full_text, target_language)  # Remove "Full Article:" prefix
                if full_audio:
                    full_file = os.path.join(temp_dir, 'audio-99.mp3')
                    with open(full_file, 'wb') as f:
                        f.write(full_audio)
                    audio_files.append(('audio-99.mp3', 'Full Article'))
                
                # Create HTML file matching English structure
                html_content = self._create_english_format_html(title, summary_text, full_text, topics, audio_files, target_language)
                html_file = os.path.join(temp_dir, 'index.html')
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                # Create search content file
                search_file = os.path.join(temp_dir, 'audiotours_search_content.txt')
                search_content = f"{title}\n\n{summary_text}\n\n{full_text}"
                with open(search_file, 'w', encoding='utf-8') as f:
                    f.write(search_content)
                
                # Create help commands text file for mobile app dialog (always English)
                help_commands_file = os.path.join(temp_dir, 'help_commands.txt')
                help_commands_text = """Voice Commands:

Say 'Play' to start or resume audio
Say 'Pause' to stop audio
Say 'Next topic' or 'Previous topic' to navigate
Say 'Forward 10 seconds' or 'Backward 5 seconds' to skip
Say 'Repeat' to restart current audio
Say 'Play topic' + number/name to jump to sections
Say 'Play summary' for article summary
Say 'Play full article' for complete text
Say 'List major topics' to hear all sections
Say 'Next article' or 'Previous article' to switch
Say 'What are my options' to hear this help again"""
                with open(help_commands_file, 'w', encoding='utf-8') as f:
                    f.write(help_commands_text)
                
                # Create short title if needed
                title_words = len(title.split())
                if title_words > 12:
                    short_title = ' '.join(title.split()[:12]) + '...'
                    short_title_file = os.path.join(temp_dir, 'audiotours_short_title.txt')
                    with open(short_title_file, 'w', encoding='utf-8') as f:
                        f.write(short_title)
                
                # Create ZIP file with same structure as English
                zip_path = os.path.join(temp_dir, 'article.zip')
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(html_file, 'index.html')
                    zipf.write(search_file, 'audiotours_search_content.txt')
                    zipf.write(help_commands_file, 'help_commands.txt')
                    if title_words > 12:
                        zipf.write(short_title_file, 'audiotours_short_title.txt')
                    for audio_file, _ in audio_files:
                        audio_path = os.path.join(temp_dir, audio_file)
                        if os.path.exists(audio_path):
                            zipf.write(audio_path, audio_file)
                
                # Read ZIP data
                with open(zip_path, 'rb') as f:
                    zip_data = f.read()
                
                logging.info(f"Created Russian article ZIP ({len(zip_data)} bytes) with {len(audio_files)} audio files matching English structure")
                return zip_data
                
        except Exception as e:
            logging.error(f"Error creating English structure ZIP: {e}")
            return None
    
    def _create_english_format_html(self, title, summary_text, full_text, topics, audio_files, target_language):
        """Generate HTML matching exact English article format"""
        
        # Create sections for each audio file
        audio_sections = ""
        for i, (audio_file, section_title) in enumerate(audio_files):
            # Determine proper audio ID based on file structure
            if audio_file == "audio_1.mp3":
                audio_id = "audio_1"
                section_class = "summary"
            elif audio_file == "audio-topics.mp3":
                audio_id = "audio-topics"
                # Hide topics list from UI - voice-only access
                audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
                continue
            elif audio_file == "audio-help.mp3":
                audio_id = "audio-help"
                # Hide help commands from UI - voice-only access
                audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
                continue
            elif audio_file == "audio-99.mp3":
                audio_id = "audio-99"
                section_class = "full-article"
            else:
                # Extract number from filename like audio-1.mp3, audio-2.mp3, etc.
                try:
                    if "-" in audio_file:
                        audio_num = audio_file.split("-")[1].split(".")[0]
                        audio_id = f"audio-{audio_num}"
                    else:
                        audio_num = audio_file.split("_")[1].split(".")[0] if "_" in audio_file else str(i+1)
                        audio_id = f"audio-{audio_num}"
                    section_class = "topic-section"
                except IndexError as e:
                    logging.error(f"Error parsing audio filename {audio_file}: {e}")
                    audio_id = f"audio-{i+1}"
                    section_class = "topic-section"
            
            # Hide major points from UI and auto-play - voice-only access
            if section_class == "topic-section":
                audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
                continue
            
            audio_sections += f'''
        <div class="section {section_class}">
            <h2>{section_title}</h2>
            <audio id="{audio_id}" controls preload="metadata">
                <source src="{audio_file}" type="audio/mpeg">
            </audio>
        </div>'''
        
        # Create HTML with exact English structure and JavaScript
        html = f'''<!DOCTYPE html>
<html lang="{target_language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .article-container {{ max-width: 800px; margin: 0 auto; }}
        audio {{ width: 100%; margin: 20px 0; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .summary {{ background-color: #f0f8ff; }}
        .topic-section {{ background-color: #f5f5f5; }}
        .full-article {{ background-color: #f9f9f9; }}
    </style>
</head>
<body>
    <div class="article-container">
        <h1>{title}</h1>
        {audio_sections}
    </div>
    
    <script>
        let currentIndex = 0;
        let audioElements = [];
        let currentAudio = null;
        let autoPlayEnabled = true;
        let timerVariable = 0;
        let timeOutParameterGlobal = 100;
        let listIsBeingRead = false;
        
        function safeSetTimeout(func, timeout) {{
            if (timerVariable < 1) {{
                timerVariable++;
                setTimeout(() => {{
                    timerVariable--;
                    timeOutParameterGlobal = 100;
                    func();
                }}, timeout);
                return "DEBUG: Timer set for " + timeout + "ms";
            }}
            return "DEBUG: Timer blocked (active=" + timerVariable + ")";
        }}
        
        document.addEventListener('DOMContentLoaded', function() {{
            audioElements = Array.from(document.querySelectorAll('audio'));
            if (audioElements.length > 0) {{
                currentAudio = audioElements[0];
                safeSetTimeout(() => playAudioByIndex(0), 1000);
            }}
            
            audioElements.forEach((audio, index) => {{
                audio.addEventListener('play', function() {{
                    audioElements.forEach((otherAudio, otherIndex) => {{
                        if (otherIndex !== index && !otherAudio.paused) {{
                            otherAudio.pause();
                            otherAudio.currentTime = 0;
                        }}
                    }});
                    currentIndex = index;
                    currentAudio = audio;
                }});
                
                audio.addEventListener('ended', function() {{
                    if (autoPlayEnabled && index < audioElements.length - 1) {{
                        let nextIndex = index + 1;
                        // Skip hidden topic sections in auto-play sequence
                        while (nextIndex < audioElements.length && audioElements[nextIndex].style.display === 'none') {{
                            nextIndex++;
                        }}
                        if (nextIndex < audioElements.length) {{
                            safeSetTimeout(() => playAudioByIndex(nextIndex), 500);
                        }}
                    }}
                }});
            }});
        }});
        
        function playAudioByIndex(index) {{
            audioElements.forEach(audio => {{
                audio.pause();
                audio.currentTime = 0;
            }});
            
            if (index >= 0 && index < audioElements.length) {{
                currentIndex = index;
                currentAudio = audioElements[index];
                currentAudio.play();
                return true;
            }}
            return false;
        }}
        
        window.playAudio = function() {{
            if (currentAudio) {{
                currentAudio.play();
                return "DEBUG: Playing currentAudio (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No currentAudio set";
        }};
        
        window.pauseAudio = function() {{
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            return "DEBUG: All audio paused (currentIndex=" + currentIndex + ", time preserved)";
        }};
        
        window.resetVoiceControlState = function() {{
            listIsBeingRead = false;
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            return "DEBUG: Voice control state reset (listIsBeingRead=false, time preserved)";
        }};
        
        window.playPoint = function(pointNumber) {{
            const topicAudio = document.getElementById('audio-' + (pointNumber + 1));
            if (topicAudio) {{
                const topicIndex = Array.from(audioElements).indexOf(topicAudio);
                if (topicIndex >= 0) {{
                    return playAudioByIndex(topicIndex) ? 'Playing topic ' + pointNumber : 'Failed to play topic';
                }}
            }}
            return 'Topic ' + pointNumber + ' not found';
        }};
        
        window.seekForward = function(seconds) {{
            if (currentAudio) {{
                const maxTime = currentAudio.duration || 0;
                currentAudio.currentTime = Math.min(maxTime, currentAudio.currentTime + seconds);
                if (currentAudio.paused) {{
                    currentAudio.play();
                }}
                return "DEBUG: Seeked forward " + seconds + "s to " + currentAudio.currentTime.toFixed(1) + "s";
            }}
            return "ERROR: No current audio";
        }};
        
        window.seekBackward = function(seconds) {{
            if (currentAudio) {{
                currentAudio.currentTime = Math.max(0, currentAudio.currentTime - seconds);
                if (currentAudio.paused) {{
                    currentAudio.play();
                }}
                return "DEBUG: Seeked backward " + seconds + "s to " + currentAudio.currentTime.toFixed(1) + "s";
            }}
            return "ERROR: No current audio";
        }};
        
        window.listPoints = function() {{
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            
            const topicsAudio = document.getElementById('audio-topics');
            if (topicsAudio) {{
                topicsAudio.currentTime = 0;
                listIsBeingRead = true;
                topicsAudio.addEventListener('ended', function() {{
                    listIsBeingRead = false;
                }}, {{ once: true }});
                
                topicsAudio.play();
                return "DEBUG: Playing topics list (listIsBeingRead=true, duration=" + (topicsAudio.duration || 'unknown') + "s, other audio times preserved)";
            }}
            return "ERROR: Topics list not found";
        }};
        
        window.isListBeingRead = function() {{
            return listIsBeingRead ? "true" : "false";
        }};
        
        window.getTopicsAudioDuration = function() {{
            const topicsAudio = document.getElementById('audio-topics');
            return topicsAudio ? (topicsAudio.duration || 0).toString() : "0";
        }};
        
        window.showHelp = function() {{
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            
            const helpAudio = document.getElementById('audio-help');
            if (helpAudio) {{
                helpAudio.currentTime = 0;
                helpAudio.play();
                return "DEBUG: Playing help commands (duration=" + (helpAudio.duration || 'unknown') + "s)";
            }}
            return "ERROR: Help audio not found";
        }};
        
        window.playFullArticle = function() {{
            const fullArticleAudio = document.getElementById('audio-99');
            if (fullArticleAudio) {{
                const fullIndex = Array.from(audioElements).indexOf(fullArticleAudio);
                if (fullIndex >= 0) {{
                    return playAudioByIndex(fullIndex) ? 'Playing full article' : 'Failed to play full article';
                }}
            }}
            return 'Full article not found';
        }};
        
        window.repeatTopic = function() {{
            if (currentAudio) {{
                currentAudio.currentTime = 0;
                return "DEBUG: Reset currentAudio to 0s (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No currentAudio to repeat";
        }};
        
        window.nextTopic = function() {{
            let nextIndex = currentIndex + 1;
            while (nextIndex < audioElements.length && audioElements[nextIndex].style.display === 'none') {{
                nextIndex++;
            }}
            
            if (nextIndex < audioElements.length) {{
                currentIndex = nextIndex;
                currentAudio = audioElements[currentIndex];
                return "DEBUG: Advanced to next (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No next topic available";
        }};
        
        window.previousTopic = function() {{
            let prevIndex = currentIndex - 1;
            while (prevIndex >= 0 && audioElements[prevIndex].style.display === 'none') {{
                prevIndex--;
            }}
            
            if (prevIndex >= 0) {{
                currentIndex = prevIndex;
                currentAudio = audioElements[currentIndex];
                return "DEBUG: Moved to previous (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No previous topic available";
        }};
    </script>
</body>
</html>'''
        return html
    # Fields that should not be spoken aloud — same set as Fix A in tour_generation_modernized.py
    _NAV_FIELD_PREFIXES = [
        'Address:', 'Coordinates:', 'Type/Specialty:', 'Specific Examples:',
        'Operational Details:'
    ]

    def _strip_nav_fields_for_tts(self, stop_text):
        """Remove structured metadata lines from stop text before sending to Polly.
        Keeps: Name, Orientation (full), and all narrative paragraphs.
        Strips: Address, Coordinates, Type/Specialty, Specific Examples, Operational Details."""
        lines = stop_text.split('\n')
        clean_lines = []
        skip_next_blank = False
        for line in lines:
            stripped = line.strip()
            is_nav = any(
                re.match(rf'^{re.escape(prefix)}', stripped, re.IGNORECASE)
                for prefix in self._NAV_FIELD_PREFIXES
            )
            if is_nav:
                skip_next_blank = True
                continue
            if skip_next_blank and stripped == '':
                skip_next_blank = False
                continue
            skip_next_blank = False
            clean_lines.append(line)
        return '\n'.join(clean_lines).strip()

    def _split_tour_content_into_stops(self, tour_content):
        """Split tour content into individual stops using the same logic as tour generation"""
        
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
                
                # Detect modernized ZIP format: separate audio_N.mp3 files (not embedded base64)
                existing_mp3s = sorted([f for f in os.listdir(extract_dir) if re.match(r'audio_\d+\.mp3', f)])
                is_modernized_format = len(existing_mp3s) > 0

                if not audio_matches and audio_files:
                    if is_modernized_format:
                        # Modernized format: overwrite audio_1.mp3, audio_2.mp3 ... with translated Polly bytes
                        logging.info(f"Modernized ZIP format detected ({len(existing_mp3s)} mp3 files). Replacing with translated audio.")
                        if len(audio_files) != len(existing_mp3s):
                            logging.warning(f"Stop count mismatch: {len(audio_files)} translated stops vs {len(existing_mp3s)} original mp3s — some stops may keep English audio")
                        for i, translated_audio_bytes in enumerate(audio_files):
                            mp3_filename = f'audio_{i+1}.mp3'
                            mp3_path = os.path.join(extract_dir, mp3_filename)
                            if translated_audio_bytes:
                                with open(mp3_path, 'wb') as f:
                                    f.write(translated_audio_bytes)
                                logging.info(f"Wrote translated audio to {mp3_filename}")
                            else:
                                logging.warning(f"No translated audio for stop {i+1}, keeping original {mp3_filename}")
                        # BUG 1 FIX: Translate HTML text (h1–h6, p) — audio replacement above
                        # only swaps MP3 files; the HTML visible text was left in English.
                        # Use h.clear() + h.append(NavigableString(...)) instead of h.string =
                        # so headings with nested tags (e.g. <h3><span>…</span>) are handled safely.
                        translated_count = 0
                        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            for h in soup.find_all(tag):
                                text = h.get_text().strip()
                                if text:
                                    h.clear()
                                    h.append(NavigableString(self.translate_text(text, target_language)))
                                    translated_count += 1
                        for p in soup.find_all('p'):
                            text = p.get_text().strip()
                            if text and len(text) > 5:
                                p.clear()
                                p.append(NavigableString(self.translate_text(text, target_language)))
                                translated_count += 1
                        logging.info(f"Translated {translated_count} HTML text elements in modernized ZIP")
                        updated_html = str(soup)
                    else:
                        # Legacy format without embedded audio — translate HTML text only
                        logging.info("No embedded audio and no separate mp3 files found, translating HTML text only")
                        translated_count = 0
                        for p in soup.find_all('p'):
                            text = p.get_text().strip()
                            if text and len(text) > 5:
                                p.clear()
                                p.append(NavigableString(self.translate_text(text, target_language)))
                                translated_count += 1
                        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            for h in soup.find_all(tag):
                                text = h.get_text().strip()
                                if text:
                                    h.clear()
                                    h.append(NavigableString(self.translate_text(text, target_language)))
                                    translated_count += 1
                        logging.info(f"Translated {translated_count} HTML elements")
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
                    
                    # Create individual translated stop text files (1-indexed to match audio_N.mp3)
                    for i, translated_stop in enumerate(translated_stops, 1):
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
        """Generate HTML with embedded translated audio data.

        NOTE (2026-05-18): Dead code — no callers in the codebase as of commit 792487c.
        The legacy fallback _translate_tour_from_zip() uses translate_zip_audio() instead.
        Kept to keep the A#55 merge diff focused; slated for removal in a post-merge
        cleanup commit. Map-button logic here is defensive — correct if ever called,
        but currently unreachable.
        """
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
        .map-btn {{ background: #2c3e50; border: none; border-radius: 50%; width: 36px; height: 36px;
                    font-size: 20px; line-height: 1;
                    cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
                    margin-left: 8px; vertical-align: middle; }}
    </style>
</head>
<body>
    <script>
        function openMap(stopNum) {{
            if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {{
                window.flutter_inappwebview.callHandler('openMap', {{stop: stopNum}});
            }}
        }}
    </script>
    <div class="tour-header">
        <h1>{tour_name}</h1>
        <span class="language-indicator">{target_language.upper()}</span>
    </div>'''
        
        for i, (stop_text, audio_data) in enumerate(zip(translated_stops, audio_files)):
            # Extract stop title from text content
            lines = stop_text.split('\n')
            stop_title = lines[0].strip() if lines else f"Stop {i+1}"
            
            # Map button — only if stop has coordinates
            map_button = ''
            if re.search(r'^Coordinates:\s*[-\d.]+\s*,\s*[-\d.]+', stop_text, re.IGNORECASE | re.MULTILINE):
                map_button = f'<button class="map-btn" onclick="openMap({i+1})" title="View on map">🗺</button>'
            
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
        {map_button}
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
    
    def _translate_tour_from_zip(self, original_tour, target_language, zip_data_override=None):
        """Fallback method for tours without stored content - uses old ZIP extraction method"""
        logging.info("Using fallback ZIP extraction method for tour translation")
        
        # Translate tour name and request string
        translated_name = self.translate_text(original_tour[1], target_language)
        translated_request = self.translate_text(original_tour[2], target_language)
        
        # Process ZIP file for audio translation — use override if provided (e.g., from R2)
        original_zip_data = zip_data_override if zip_data_override else original_tour[3]
        if not original_zip_data:
            logging.error(f"Tour {original_tour[0]} has no ZIP data (audio_tour is NULL) — cannot translate")
            return None
        
        # Convert memoryview/buffer to bytes if needed
        if hasattr(original_zip_data, 'tobytes'):
            original_zip_data = original_zip_data.tobytes()
        elif not isinstance(original_zip_data, bytes):
            original_zip_data = bytes(original_zip_data)
        
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
        elif content_type == 'article':
            translated_id = translation_service.translate_article(content_id, lang)
        else:
            translated_id = None
        
        if translated_id:
            # Include translated tour_name so the mobile app can display the correct title
            translated_name = None
            try:
                conn = translation_service.get_db_connection()
                cur = conn.cursor()
                table = 'audio_tours' if content_type == 'tour' else 'article_requests'
                name_col = 'tour_name' if content_type == 'tour' else 'request_string'
                cur.execute(f"SELECT {name_col} FROM {table} WHERE id = %s", (translated_id,))
                row = cur.fetchone()
                if row:
                    translated_name = row[0]
                cur.close()
                conn.close()
            except Exception as e:
                logging.warning(f"Could not fetch translated name for {translated_id}: {e}")
            
            result_entry = {'status': 'translated', 'id': translated_id}
            if translated_name:
                result_entry['name'] = translated_name
            results[lang] = result_entry
        else:
            results[lang] = {'status': 'failed', 'id': None}
    
    return jsonify({
        'status': 'completed',
        'translations': results
    })
@app.route('/translate', methods=['POST', 'OPTIONS'])
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
    port = int(os.getenv('PORT', '5030'))
    app.run(host='0.0.0.0', port=port, debug=False)