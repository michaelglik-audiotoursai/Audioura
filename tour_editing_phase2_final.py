"""
Phase 2 Tour Editing Backend - REQ-016 Final Implementation
Clean final state processing with complete tour generation
"""
SERVICE_VERSION = "1.2.6.233"

import os
import json
import uuid
import zipfile
import shutil
import requests
import psycopg2
import re
import html
import base64
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)

TOURS_DIR = "/app/tours"
POLLY_TTS_URL = "http://polly-tts-1:5018"
MAX_AUDIO_SIZE_MB = int(os.getenv('CUSTOM_AUDIO_MAX_SIZE_MB', 5))
MAX_AUDIO_SIZE = MAX_AUDIO_SIZE_MB * 1024 * 1024  # Convert to bytes

def clean_markdown_formatting(text):
    """Remove markdown formatting characters that interfere with TTS"""
    if not text or not isinstance(text, str):
        return ""
    
    # Remove bold markdown: **text** → text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    
    # Remove italic markdown: __text__ → text
    text = re.sub(r'__([^_]+)__', r'\1', text)
    
    # Remove single asterisk emphasis: *text* → text
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    
    # Remove single underscore emphasis: _text_ → text
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    return text

def sanitize_user_input(text):
    """Sanitize user input to prevent injection attacks and filesystem issues"""
    if not text or not isinstance(text, str):
        return ""
    
    # Remove null bytes and control characters
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    
    # Clean markdown formatting for better TTS and display
    text = clean_markdown_formatting(text)
    
    # Remove SQL injection patterns
    sql_patterns = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|SCRIPT)\b)',
        r'(--|#|/\*|\*/)',
        r'(\bOR\b.*\b1\s*=\s*1\b)',
        r'(\bAND\b.*\b1\s*=\s*1\b)',
        r'([\'";])',
    ]
    
    for pattern in sql_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Remove script tags and javascript
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    
    # Replace filesystem-dangerous characters for path safety
    text = re.sub(r'[<>:"/\\|?*]', '_', text)
    
    # Limit length to prevent DoS
    text = text[:10000]
    
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def get_db_connection():
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def resolve_numeric_to_uuid_directory(tour_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tour_name FROM audio_tours WHERE id = %s", (int(tour_id),))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            tour_name = result[0].lower()
            tours_dir = Path(TOURS_DIR)
            
            keywords = ['harvard', 'university', 'campus', 'cambridge'] if 'harvard' in tour_name else []
            if 'american' in tour_name and 'wing' in tour_name:
                keywords = ['american', 'wing', 'mfa']
            if 'boston' in tour_name and 'library' in tour_name:
                keywords = ['boston', 'library']
            
            for item in tours_dir.iterdir():
                if item.is_dir():
                    item_name_lower = item.name.lower()
                    if keywords and any(keyword in item_name_lower for keyword in keywords):
                        return item
                        
        return None
    except Exception as e:
        print(f"Error resolving numeric tour {tour_id}: {e}")
        return None

def resolve_tour_to_directory(tour_identifier):
    tours_dir = Path(TOURS_DIR)
    
    exact_path = tours_dir / tour_identifier
    if exact_path.exists():
        return exact_path
    
    if tour_identifier.isdigit():
        return resolve_numeric_to_uuid_directory(tour_identifier)
    
    uuid_part = None
    if '-' in tour_identifier:
        uuid_part = tour_identifier.split('-')[0]
    elif len(tour_identifier) >= 8:
        uuid_part = tour_identifier[:8]
    
    if uuid_part:
        for item in tours_dir.iterdir():
            if item.is_dir() and uuid_part in item.name:
                return item
    
    return None

def has_custom_audio(tour_id, stop_number, user_id=None):
    """Check if custom audio exists for a stop (safe fallback)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if custom_audio_files table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'custom_audio_files'
            )
        """)
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            cur.close()
            conn.close()
            return None
        
        if user_id:
            cur.execute("""
                SELECT file_path FROM custom_audio_files 
                WHERE tour_id = %s AND stop_number = %s AND user_id = %s AND is_active = true
                ORDER BY likes_count DESC, version_number DESC LIMIT 1
            """, (tour_id, stop_number, user_id))
        else:
            cur.execute("""
                SELECT file_path FROM custom_audio_files 
                WHERE tour_id = %s AND stop_number = %s AND is_active = true
                ORDER BY likes_count DESC, version_number DESC LIMIT 1
            """, (tour_id, stop_number))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result and os.path.exists(result[0]):
            return result[0]
        return None
    except Exception as e:
        # Silent fallback - don't break existing functionality
        return None

def detect_audio_format(audio_bytes):
    """Detect audio format from file headers with debug logging"""
    if len(audio_bytes) < 12:
        print(f"AUDIO_FORMAT: File too small ({len(audio_bytes)} bytes)")
        return "unknown"
    
    # Debug logging
    first_20 = audio_bytes[:20]
    print(f"AUDIO_FORMAT: File size: {len(audio_bytes)} bytes")
    print(f"AUDIO_FORMAT: First 20 bytes (hex): {first_20.hex()}")
    print(f"AUDIO_FORMAT: First 20 bytes (ascii): {first_20}")
    
    # WebM detection (HTML5 MediaRecorder primary format)
    if audio_bytes[:4] == b'\x1a\x45\xdf\xa3':  # EBML header
        print(f"AUDIO_FORMAT: Detected WebM format (EBML header)")
        return "webm"
    
    # MP4 detection (HTML5 MediaRecorder fallback)
    if (audio_bytes[4:8] == b'ftyp' or  # MP4 file type box
        audio_bytes[4:12] == b'ftypmp42' or  # MP4 v2
        audio_bytes[4:12] == b'ftypisom' or  # ISO base media
        b'mp4' in audio_bytes[:20].lower()):
        print(f"AUDIO_FORMAT: Detected MP4 format")
        return "mp4"
    
    # WAV detection (legacy flutter_sound)
    if audio_bytes[:4] == b'RIFF':
        print(f"AUDIO_FORMAT: Found RIFF header")
        if len(audio_bytes) >= 12 and audio_bytes[8:12] == b'WAVE':
            print(f"AUDIO_FORMAT: Found WAVE identifier at offset 8")
            return "wav"
        if b'WAVE' in audio_bytes[:20]:
            print(f"AUDIO_FORMAT: Found WAVE identifier in first 20 bytes")
            return "wav"
    
    # MP3 detection
    if (audio_bytes[:3] == b'ID3' or 
        audio_bytes[:2] == b'\xff\xfb' or 
        audio_bytes[:2] == b'\xff\xf3' or 
        audio_bytes[:2] == b'\xff\xf2'):
        print(f"AUDIO_FORMAT: Detected MP3 format")
        return "mp3"
    
    # AAC detection
    if (audio_bytes[:2] == b'\xff\xf1' or 
        audio_bytes[:2] == b'\xff\xf9' or 
        audio_bytes[:4] == b'ADTS'):
        print(f"AUDIO_FORMAT: Detected AAC format")
        return "aac"
    
    # Fallback WAV detection
    if b'WAVE' in audio_bytes[:50]:
        print(f"AUDIO_FORMAT: Found WAVE identifier in extended range")
        return "wav"
    
    print(f"AUDIO_FORMAT: Unknown format - no matching patterns found")
    return "unknown"

def check_ffmpeg_available():
    """Check if ffmpeg is available"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def convert_audio_to_mp3(audio_bytes, source_format):
    """Convert audio to MP3 format using ffmpeg"""
    if source_format == "mp3":
        return audio_bytes, "mp3"  # No conversion needed
    
    if not check_ffmpeg_available():
        raise Exception("ffmpeg not available for audio conversion")
    
    temp_input = None
    temp_output = None
    
    try:
        # Determine file extension for temp file
        ext_map = {"webm": ".webm", "mp4": ".mp4", "wav": ".wav", "aac": ".aac"}
        file_ext = ext_map.get(source_format, f".{source_format}")
        
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_input:
            temp_input.write(audio_bytes)
            temp_input_path = temp_input.name
        
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_output:
            temp_output_path = temp_output.name
        
        # Fixed ffmpeg command for WebM/MP4 support
        cmd = [
            'ffmpeg', '-i', temp_input_path,
            '-acodec', 'libmp3lame', '-ab', '128k', '-ar', '44100',
            '-ac', '1',  # Mono output for smaller files
            '-y', temp_output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"CUSTOM_AUDIO: ffmpeg stderr: {result.stderr}")
            raise Exception(f"ffmpeg conversion failed: {result.stderr}")
        
        # Read converted file
        with open(temp_output_path, 'rb') as f:
            converted_bytes = f.read()
        
        print(f"CUSTOM_AUDIO: Conversion successful - {source_format.upper()}({len(audio_bytes)/1024:.1f}KB) -> MP3({len(converted_bytes)/1024:.1f}KB)")
        
        return converted_bytes, "mp3"
        
    except MemoryError:
        print("CUSTOM_AUDIO: Memory conversion failed, using file-based conversion")
        raise Exception("Audio file too large for conversion")
    
    finally:
        # Clean up temporary files
        try:
            if temp_input and os.path.exists(temp_input_path):
                os.unlink(temp_input_path)
            if temp_output and os.path.exists(temp_output_path):
                os.unlink(temp_output_path)
        except Exception as cleanup_e:
            print(f"Cleanup warning: {cleanup_e}")

def concatenate_mp3_files(mp3_files_data):
    """Concatenate multiple MP3 files using ffmpeg"""
    if not mp3_files_data:
        raise Exception("No MP3 files to concatenate")
    
    if len(mp3_files_data) == 1:
        return mp3_files_data[0]  # Single file, no concatenation needed
    
    temp_files = []
    temp_output = None
    
    try:
        # Create temporary files for each MP3
        for i, mp3_data in enumerate(mp3_files_data):
            temp_file = tempfile.NamedTemporaryFile(suffix=f'_part_{i}.mp3', delete=False)
            temp_file.write(mp3_data)
            temp_file.close()
            temp_files.append(temp_file.name)
        
        # Create output file
        temp_output = tempfile.NamedTemporaryFile(suffix='_concatenated.mp3', delete=False)
        temp_output.close()
        
        # Create ffmpeg concat file list
        concat_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        for temp_file in temp_files:
            concat_file.write(f"file '{temp_file}'\n")
        concat_file.close()
        
        # Run ffmpeg concatenation
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file.name,
            '-c', 'copy', '-y', temp_output.name
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"MULTI_PART: ffmpeg concat stderr: {result.stderr}")
            raise Exception(f"MP3 concatenation failed: {result.stderr}")
        
        # Read concatenated file
        with open(temp_output.name, 'rb') as f:
            concatenated_bytes = f.read()
        
        print(f"MULTI_PART: Concatenation successful - {len(mp3_files_data)} parts -> {len(concatenated_bytes)/1024:.1f}KB")
        
        return concatenated_bytes
        
    finally:
        # Clean up all temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                print(f"Cleanup warning: {e}")
        
        if temp_output and os.path.exists(temp_output.name):
            try:
                os.unlink(temp_output.name)
            except Exception as e:
                print(f"Cleanup warning: {e}")
        
        try:
            if 'concat_file' in locals() and os.path.exists(concat_file.name):
                os.unlink(concat_file.name)
        except Exception as e:
            print(f"Cleanup warning: {e}")

def process_multi_part_audio(audio_parts, tour_id, stop_number, user_id="default"):
    """Process multi-part audio with partial failure handling"""
    if not audio_parts:
        raise Exception("No audio parts provided")
    
    print(f"MULTI_PART: Processing {len(audio_parts)} parts for stop {stop_number}")
    
    # Calculate total size
    total_size = sum(len(base64.b64decode(part['data'])) for part in audio_parts)
    if total_size > MAX_AUDIO_SIZE:
        size_mb = total_size / 1024 / 1024
        raise Exception(json.dumps({
            "error": "FILE_SIZE_EXCEEDED",
            "message": f"Total audio size exceeds {MAX_AUDIO_SIZE_MB}MB limit. Current: {size_mb:.1f}MB",
            "details": {
                "max_size_mb": MAX_AUDIO_SIZE_MB,
                "current_size_mb": round(size_mb, 1),
                "part_count": len(audio_parts)
            }
        }))
    
    converted_parts = []
    warnings = []
    
    # Convert each part to MP3
    for i, part in enumerate(audio_parts):
        try:
            part_bytes = base64.b64decode(part['data'])
            part_format = detect_audio_format(part_bytes)
            
            print(f"MULTI_PART: Part {i+1}/{len(audio_parts)} - {part_format.upper()} ({len(part_bytes)/1024:.1f}KB)")
            
            if part_format == "unknown":
                warnings.append(f"Part {i+1}: Unknown format, skipped")
                continue
            
            converted_bytes, _ = convert_audio_to_mp3(part_bytes, part_format)
            converted_parts.append(converted_bytes)
            
        except Exception as e:
            warning_msg = f"Part {i+1}: Conversion failed - {str(e)[:100]}"
            warnings.append(warning_msg)
            print(f"MULTI_PART: {warning_msg}")
            continue
    
    if not converted_parts:
        raise Exception("No audio parts could be converted successfully")
    
    # Concatenate converted parts
    try:
        final_mp3 = concatenate_mp3_files(converted_parts)
    except Exception as e:
        raise Exception(f"Failed to concatenate converted parts: {str(e)}")
    
    # Save final MP3
    custom_dir = Path("/app/custom_audio")
    custom_dir.mkdir(exist_ok=True)
    
    filename = f"tour_{tour_id}_stop_{stop_number}_user_{user_id}_{int(time.time())}_multipart.mp3"
    file_path = custom_dir / filename
    
    with open(file_path, 'wb') as f:
        f.write(final_mp3)
    
    print(f"MULTI_PART: Final MP3 saved: {filename} ({len(final_mp3)/1024:.1f}KB)")
    
    # Store in database if table exists
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'custom_audio_files'
            )
        """)
        table_exists = cur.fetchone()[0]
        
        if table_exists:
            cur.execute("""
                INSERT INTO custom_audio_files 
                (tour_id, stop_number, user_id, file_path, version_number, is_active, file_size)
                VALUES (%s, %s, %s, %s, 1, true, %s)
            """, (tour_id, stop_number, user_id, str(file_path), len(final_mp3)))
            conn.commit()
        
        cur.close()
        conn.close()
    except Exception as db_e:
        print(f"Database storage failed (non-critical): {db_e}")
    
    return str(file_path), warnings

def save_custom_audio_from_base64(audio_data, tour_id, stop_number, user_id="default", audio_parts=None):
    """Save base64 audio data with format conversion support and multi-part processing"""
    try:
        # Handle multi-part audio
        if audio_parts:
            print(f"MULTI_PART: Processing {len(audio_parts)} audio parts for stop {stop_number}")
            file_path, warnings = process_multi_part_audio(audio_parts, tour_id, stop_number, user_id)
            return file_path, warnings
        
        # Handle single audio file (existing logic)
        audio_bytes = base64.b64decode(audio_data)
        
        # Check file size limit
        if len(audio_bytes) > MAX_AUDIO_SIZE:
            size_mb = len(audio_bytes) / 1024 / 1024
            raise Exception(json.dumps({
                "error": "FILE_SIZE_EXCEEDED",
                "message": f"Audio file exceeds maximum size limit of {MAX_AUDIO_SIZE_MB}MB. Current file: {size_mb:.1f}MB",
                "details": {
                    "max_size_mb": MAX_AUDIO_SIZE_MB,
                    "current_size_mb": round(size_mb, 1),
                    "upgrade_available": True,
                    "admin_contact": "Contact administrator for increased limits for paying customers"
                }
            }))
        
        # Detect audio format
        source_format = detect_audio_format(audio_bytes)
        print(f"CUSTOM_AUDIO: Detected format: {source_format.upper()}")
        
        if source_format == "unknown":
            raise Exception(json.dumps({
                "error": "UNSUPPORTED_FORMAT",
                "message": "Audio format not supported",
                "details": {
                    "detected_format": "unknown",
                    "supported_formats": ["webm", "mp4", "mp3", "wav", "aac"],
                    "recommendation": "Please record in WebM, MP4, MP3, WAV, or AAC format"
                }
            }))
        
        # Convert to MP3 if needed
        try:
            converted_bytes, final_format = convert_audio_to_mp3(audio_bytes, source_format)
        except Exception as conv_e:
            print(f"CUSTOM_AUDIO: Conversion failed - {conv_e}")
            raise Exception(json.dumps({
                "error": "CONVERSION_FAILED",
                "message": "Failed to convert audio format to MP3",
                "details": {
                    "source_format": source_format,
                    "target_format": "mp3",
                    "error_reason": str(conv_e),
                    "supported_formats": ["mp3", "wav", "aac"]
                }
            }))
        
        # Create custom audio directory
        custom_dir = Path("/app/custom_audio")
        custom_dir.mkdir(exist_ok=True)
        
        # Generate filename
        filename = f"tour_{tour_id}_stop_{stop_number}_user_{user_id}_{int(time.time())}.mp3"
        file_path = custom_dir / filename
        
        # Save converted MP3 file
        with open(file_path, 'wb') as f:
            f.write(converted_bytes)
        
        print(f"CUSTOM_AUDIO: MP3 file stored: {filename}")
        
        # Store in database (if custom_audio_files table exists)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Check if table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'custom_audio_files'
                )
            """)
            table_exists = cur.fetchone()[0]
            
            if table_exists:
                cur.execute("""
                    INSERT INTO custom_audio_files 
                    (tour_id, stop_number, user_id, file_path, version_number, is_active, file_size)
                    VALUES (%s, %s, %s, %s, 1, true, %s)
                """, (tour_id, stop_number, user_id, str(file_path), len(converted_bytes)))
                conn.commit()
            
            cur.close()
            conn.close()
        except Exception as db_e:
            print(f"Database storage failed (non-critical): {db_e}")
        
        return str(file_path), []  # Return empty warnings for single file
        
    except Exception as e:
        error_str = str(e)
        # Check if it's a JSON error message
        if error_str.startswith('{'):
            raise Exception(error_str)  # Re-raise JSON error as-is
        else:
            print(f"Custom audio save failed: {e}")
            return None, []

def generate_audio_for_stop(tour_path, stop_number, text_content, tour_id=None, user_id=None, generate_flag=True, custom_audio_data=None, audio_parts=None):
    """Generate audio with flag coordination, format conversion, and multi-part support"""
    # Handle multi-part audio upload
    if audio_parts:
        try:
            custom_audio_path, warnings = save_custom_audio_from_base64(None, tour_id or "unknown", stop_number, user_id or "default", audio_parts)
            if custom_audio_path and os.path.exists(custom_audio_path):
                audio_file = tour_path / f"audio_{stop_number}.mp3"
                shutil.copy2(custom_audio_path, audio_file)
                print(f"Using multi-part custom audio for stop {stop_number}")
                return "user_recorded", warnings
        except Exception as e:
            error_str = str(e)
            if error_str.startswith('{'):
                raise Exception(error_str)
            else:
                print(f"Multi-part audio upload failed: {e}")
                return "error", []
    
    # Handle single custom audio upload with format conversion
    if custom_audio_data:
        try:
            custom_audio_path, warnings = save_custom_audio_from_base64(custom_audio_data, tour_id or "unknown", stop_number, user_id or "default")
            if custom_audio_path and os.path.exists(custom_audio_path):
                audio_file = tour_path / f"audio_{stop_number}.mp3"
                shutil.copy2(custom_audio_path, audio_file)
                print(f"Using uploaded custom audio for stop {stop_number}")
                return "user_recorded", warnings
        except Exception as e:
            error_str = str(e)
            # Check if it's a JSON error message from format conversion
            if error_str.startswith('{'):
                # Return the JSON error for proper handling by the endpoint
                raise Exception(error_str)
            else:
                print(f"Custom audio upload failed: {e}")
                return "error", []
    
    # Check generate_audio_from_text flag
    if not generate_flag:
        # Keep existing audio - check for custom audio first
        if tour_id:
            try:
                custom_audio_path = has_custom_audio(tour_id, stop_number, user_id)
                if custom_audio_path:
                    audio_file = tour_path / f"audio_{stop_number}.mp3"
                    shutil.copy2(custom_audio_path, audio_file)
                    print(f"Preserving custom audio for stop {stop_number}")
                    return "user_recorded", []
            except Exception as e:
                print(f"Custom audio check failed: {e}")
        
        # Keep existing TTS audio if available
        existing_audio = tour_path / f"audio_{stop_number}.mp3"
        if existing_audio.exists():
            print(f"Preserving existing audio for stop {stop_number}")
            return "tts_generated", []
    
    # Generate new TTS audio (flag=true or no existing audio)
    try:
        tts_response = requests.post(f"{POLLY_TTS_URL}/synthesize", json={
            "text": text_content,
            "voice": "Joanna",
            "format": "mp3"
        }, timeout=30)
        
        if tts_response.status_code == 200:
            audio_file = tour_path / f"audio_{stop_number}.mp3"
            with open(audio_file, 'wb') as f:
                f.write(tts_response.content)
            print(f"Generated TTS audio for stop {stop_number}")
            return "tts_generated", []
        return "error", []
    except Exception as e:
        print(f"Audio generation failed for stop {stop_number}: {e}")
        return "error", []

def create_clean_html(tour_path, final_stops):
    """Create clean HTML focused on audio controls"""
    html_file = tour_path / "index.html"
    
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audio Tour</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; color: #333; margin-bottom: 30px; }
        .stop-item { 
            background: white; 
            margin: 15px 0; 
            padding: 20px; 
            border-radius: 8px; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stop-title { 
            font-size: 1.3em; 
            font-weight: bold; 
            color: #2c3e50; 
            margin-bottom: 15px; 
        }
        audio { 
            width: 100%; 
            height: 40px;
            margin: 10px 0;
        }
        .stop-counter {
            background: #3498db;
            color: white;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-right: 10px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Audio Tour</h1>
'''
    
    for stop_num in sorted(final_stops):
        text_file = tour_path / f"audio_{stop_num}.txt"
        if text_file.exists():
            try:
                with open(text_file, 'r', encoding='utf-8') as f:
                    text_content = f.read().strip()
                
                title = text_content.split('\n')[0][:50] + "..." if len(text_content.split('\n')[0]) > 50 else text_content.split('\n')[0]
                
                html_content += f'''        <div class="stop-item">
            <div class="stop-title">
                <span class="stop-counter">{stop_num}</span>
                {title}
            </div>
            <audio id="audio{stop_num}" controls preload="metadata">
                <source src="audio_{stop_num}.mp3" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio>
        </div>
'''
            except Exception as e:
                print(f"Error reading stop {stop_num}: {e}")
    
    html_content += '''    </div>
    
    <script>
        // Voice Control JavaScript Functions
        var currentStopIndex = 0;
        var totalStops = ''' + str(len(final_stops)) + ''';
        var audioElements = [];
        
        // Initialize audio elements array (0-based indexing)
        document.addEventListener('DOMContentLoaded', function() {
            var stopNumbers = [''' + ','.join(map(str, sorted(final_stops))) + '''];
            for (let i = 0; i < stopNumbers.length; i++) {
                var audioElement = document.getElementById('audio' + stopNumbers[i]);
                audioElements.push(audioElement);
                
                // Update currentStopIndex when manually played
                audioElement.addEventListener('play', function() {
                    currentStopIndex = i;
                });
            }
        });
        
        window.playAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].play();
                return "success";
            }
            return "error";
        };
        
        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return "success";
            }
            return "error";
        };
        
        window.nextStop = function() {
            if (currentStopIndex < totalStops - 1) {
                pauseAllAudio();
                currentStopIndex++;
                audioElements[currentStopIndex].play();
                return "success";
            }
            return "error";
        };
        
        window.previousStop = function() {
            if (currentStopIndex > 0) {
                pauseAllAudio();
                currentStopIndex--;
                audioElements[currentStopIndex].play();
                return "success";
            }
            return "error";
        };
        
        window.goToStop = function(stopNumber) {
            if (stopNumber >= 1 && stopNumber <= totalStops) {
                pauseAllAudio();
                currentStopIndex = stopNumber - 1;
                audioElements[currentStopIndex].play();
                return "success";
            }
            return "error";
        };
        
        window.pauseAllAudio = function() {
            audioElements.forEach(function(audio) {
                if (audio) audio.pause();
            });
            return "success";
        };
        
        window.repeatStop = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].currentTime = 0;
                audioElements[currentStopIndex].play();
                return "success";
            }
            return "error";
        };
        
        window.initializeAudio = function() {
            currentStopIndex = 0;
            return "success";
        };
    </script>
</body>
</html>'''
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

def create_complete_tour(original_tour_path, final_stops_data, tour_id=None):
    """Create complete tour with flag coordination support"""
    new_uuid = str(uuid.uuid4())
    new_uuid_prefix = new_uuid.split('-')[0]
    
    original_name = original_tour_path.name
    if '_' in original_name:
        name_parts = original_name.split('_')
        name_parts[-1] = new_uuid_prefix
        new_dir_name = '_'.join(name_parts)
    else:
        new_dir_name = f"{original_name}_{new_uuid_prefix}"
    
    new_tour_path = original_tour_path.parent / new_dir_name
    new_tour_path.mkdir(exist_ok=True)
    
    # Create mapping of original stop positions to track audio files
    original_stops = {}
    for f in original_tour_path.glob("audio_*.txt"):
        stop_num = int(f.stem.split('_')[1])
        with open(f, 'r', encoding='utf-8') as file:
            original_stops[stop_num] = file.read().strip()
    
    final_stops = set()
    
    # Process all final stops with flag coordination
    for stop_data in final_stops_data:
        stop_number = stop_data['stop_number']
        text_content = stop_data['text_content']
        is_added = stop_data['is_added']
        generate_flag = stop_data.get('generate_audio_from_text', True)
        custom_audio_data = stop_data.get('custom_audio_data')
        has_custom_audio_flag = stop_data.get('has_custom_audio', False)
        custom_audio_path = stop_data.get('custom_audio_path')
        audio_parts = stop_data.get('audio_parts')
        
        final_stops.add(stop_number)
        
        # Create text file
        text_file = new_tour_path / f"audio_{stop_number}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        # REQ-022: Handle audio with custom audio support (including multi-part)
        if audio_parts:
            # Multi-part audio upload
            audio_result, warnings = generate_audio_for_stop(new_tour_path, stop_number, text_content, tour_id, None, True, None, audio_parts)
            if warnings:
                print(f"REQ-037: Multi-part audio warnings for stop {stop_number}: {warnings}")
            print(f"REQ-037: Multi-part audio result for stop {stop_number}: {audio_result}")
        elif custom_audio_data:
            # Single custom audio upload via base64 data
            audio_result, warnings = generate_audio_for_stop(new_tour_path, stop_number, text_content, tour_id, None, True, custom_audio_data)
            print(f"REQ-022: Custom audio upload result for stop {stop_number}: {audio_result}")
        elif has_custom_audio_flag and custom_audio_path:
            # Custom audio via file path (REQ-022)
            try:
                if os.path.exists(custom_audio_path):
                    audio_file = new_tour_path / f"audio_{stop_number}.mp3"
                    shutil.copy2(custom_audio_path, audio_file)
                    print(f"REQ-022: Copied custom audio from {custom_audio_path} for stop {stop_number}")
                else:
                    print(f"REQ-022: Custom audio path not found: {custom_audio_path}, generating TTS")
                    generate_audio_for_stop(new_tour_path, stop_number, text_content, tour_id, None, True)
            except Exception as e:
                print(f"REQ-022: Error copying custom audio: {e}, generating TTS")
                generate_audio_for_stop(new_tour_path, stop_number, text_content, tour_id, None, True)
        elif is_added:
            # New stops always generate audio
            generate_audio_for_stop(new_tour_path, stop_number, text_content, tour_id, None, True)
        elif generate_flag:
            # Flag true - regenerate audio from text
            generate_audio_for_stop(new_tour_path, stop_number, text_content, tour_id, None, True)
        else:
            # Flag false - preserve existing audio
            original_audio_found = False
            for orig_stop_num, orig_content in original_stops.items():
                if orig_content == text_content:
                    original_audio = original_tour_path / f"audio_{orig_stop_num}.mp3"
                    if original_audio.exists():
                        new_audio = new_tour_path / f"audio_{stop_number}.mp3"
                        shutil.copy2(original_audio, new_audio)
                        original_audio_found = True
                        break
            
            if not original_audio_found:
                # No existing audio found, generate new
                generate_audio_for_stop(new_tour_path, stop_number, text_content, tour_id, None, True)
    
    # Copy other files from original tour (excluding audio/text files)
    for file_path in original_tour_path.rglob('*'):
        if file_path.is_file() and not file_path.name.startswith('audio_') and file_path.name != 'index.html':
            relative_path = file_path.relative_to(original_tour_path)
            dest_path = new_tour_path / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_path)
    
    # Create clean HTML
    create_clean_html(new_tour_path, final_stops)
    
    # Create ZIP file
    zip_path = new_tour_path.parent / f"{new_tour_path.name}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in new_tour_path.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(new_tour_path)
                zipf.write(file_path, arcname)
    
    return {
        'new_tour_id': new_uuid,
        'tour_path': new_tour_path
    }

@app.route('/tour/<tour_id>/bulk-save', methods=['POST'])
def bulk_save_stops(tour_id):
    """REQ-020: Bulk save with audio generation flag coordination"""
    data = request.json
    stops = data.get('stops', [])
    
    print(f"\n==== REQ-022/023 DEBUG: RECEIVED REQUEST ====")
    print(f"Tour ID: {tour_id}")
    print(f"Number of stops: {len(stops)}")
    for i, stop in enumerate(stops):
        print(f"Stop {i+1}: number={stop.get('stop_number')}, action='{stop.get('action')}', flag={stop.get('generate_audio_from_text')}, has_custom_audio={stop.get('has_custom_audio')}, custom_audio_data={bool(stop.get('custom_audio_data'))}, custom_audio_path={stop.get('custom_audio_path')}")
    
    if not stops:
        # REQ-024: Proper validation error response
        return jsonify({
            "status": "error",
            "message": "Tour stops data is required for saving",
            "error_code": "VALIDATION_FAILED",
            "recoverable": True,
            "suggested_action": "Please ensure tour has at least one stop and try again"
        }), 400
    
    tour_path = resolve_tour_to_directory(tour_id)
    if not tour_path:
        # REQ-024: Proper not found error response
        return jsonify({
            "status": "error",
            "message": f"Tour with ID '{tour_id}' could not be found for bulk save operation",
            "error_code": "TOUR_NOT_FOUND",
            "recoverable": False,
            "suggested_action": "Please verify the tour ID and try again, or contact support"
        }), 404
    
    try:
        # Get original stops
        original_stops = set(int(f.stem.split('_')[1]) for f in tour_path.glob("audio_*.txt"))
        
        final_stops_data = []
        response_stops = []
        
        # Process each stop with flag coordination
        for stop_data in stops:
            stop_number = stop_data.get('stop_number')
            text = sanitize_user_input(stop_data.get('text', ''))
            action = str(stop_data.get('action', '')).lower()
            generate_flag = stop_data.get('generate_audio_from_text', True)  # Default true
            
            # REQ-022: Handle custom audio upload fields
            custom_audio_data = stop_data.get('custom_audio_data')
            has_custom_audio_flag = stop_data.get('has_custom_audio', False)
            custom_audio_path = stop_data.get('custom_audio_path')
            audio_parts = stop_data.get('audio_parts')  # Multi-part audio support
            
            print(f"REQ-022 DEBUG: Stop {stop_number} - has_custom_audio={has_custom_audio_flag}, custom_audio_path={custom_audio_path}, custom_audio_data={bool(custom_audio_data)}, audio_parts={bool(audio_parts)}")
            
            # REQ-023: Handle proper action values
            print(f"REQ-023 DEBUG: Stop {stop_number} - action='{action}' (type: {type(stop_data.get('action'))})")
            
            # Skip deleted stops
            if action == 'delete':
                print(f"REQ-023: Skipping deleted stop {stop_number}")
                continue
            
            # CRITICAL FIX: Handle action:unchanged properly for reordering
            if action == 'unchanged':
                # For unchanged stops, use the text content from mobile app (which has the right content for the new position)
                print(f"UNCHANGED: Using mobile app content for stop {stop_number} at new position")
                final_stops_data.append({
                    'stop_number': stop_number,
                    'text_content': text,  # Use text from mobile app (correct content for new position)
                    'is_added': False,
                    'generate_audio_from_text': False,  # Preserve original audio
                    'action': 'unchanged'
                })
                
                # Add to response_stops for unchanged stops
                response_stops.append({
                    'stop_number': stop_number,
                    'generate_audio_from_text': False,
                    'audio_source': "tts_generated",  # Preserved existing
                    'text_updated': False,  # Text not updated
                    'audio_updated': False,  # Audio not updated
                    'has_custom_audio': False
                })
                continue
            
            # Determine if this is an added stop
            is_added = (action == 'add') or (stop_number not in original_stops)
            
            # REQ-022: Custom audio processing logic (including multi-part)
            if has_custom_audio_flag or custom_audio_data or audio_parts:
                generate_flag = False  # Custom audio overrides text generation
                print(f"REQ-022: Custom audio detected for stop {stop_number}, setting generate_flag=False")
            
            # Add to final stops data
            final_stops_data.append({
                'stop_number': stop_number,
                'text_content': text,
                'is_added': is_added,
                'generate_audio_from_text': generate_flag,
                'custom_audio_data': custom_audio_data,
                'has_custom_audio': has_custom_audio_flag,
                'custom_audio_path': custom_audio_path,
                'audio_parts': audio_parts
            })
            
            # REQ-026: Return error if custom audio failed instead of claiming success
            audio_source = "tts_generated"  # Default
            
            # Only claim user_recorded if we actually have audio data to process
            if custom_audio_data or audio_parts:
                audio_source = "user_recorded"
                print(f"REQ-022: Setting audio_source=user_recorded for stop {stop_number}")
            elif has_custom_audio_flag and not custom_audio_data and not audio_parts:
                # REQ-026: Custom audio flag without data = error condition
                return jsonify({
                    "status": "error",
                    "message": f"Custom audio requested for stop {stop_number} but no audio data provided",
                    "error_code": "MISSING_AUDIO_DATA",
                    "recoverable": True,
                    "suggested_action": "Please record audio and try again, or disable custom audio for this stop"
                }), 400
            elif not generate_flag and not custom_audio_data and not audio_parts:
                # Check if existing custom audio exists
                if has_custom_audio(tour_id, stop_number):
                    audio_source = "user_recorded"
            
            response_stops.append({
                'stop_number': stop_number,
                'generate_audio_from_text': generate_flag,
                'audio_source': audio_source,
                'text_updated': True,
                'audio_updated': generate_flag or bool(custom_audio_data) or has_custom_audio_flag or bool(audio_parts),
                'has_custom_audio': has_custom_audio_flag or bool(audio_parts)
            })
        
        # Add unchanged original stops not in the request
        for stop_num in original_stops:
            if not any(s['stop_number'] == stop_num for s in final_stops_data):
                text_file = tour_path / f"audio_{stop_num}.txt"
                if text_file.exists():
                    with open(text_file, 'r', encoding='utf-8') as f:
                        original_content = f.read().strip()
                    
                    # Preserve original audio - do NOT regenerate TTS
                    final_stops_data.append({
                        'stop_number': stop_num,
                        'text_content': original_content,
                        'is_added': False,
                        'generate_audio_from_text': False  # Preserve original audio
                    })
        
        # Sort by stop_number but preserve mobile app's intended positions
        final_stops_data.sort(key=lambda x: x['stop_number'])
        
        # CRITICAL FIX: Renumber stops sequentially to eliminate gaps
        print(f"RENUMBER: Before - stops: {[s['stop_number'] for s in final_stops_data]}")
        for i, stop_data in enumerate(final_stops_data):
            old_number = stop_data['stop_number']
            new_number = i + 1  # Sequential: 1, 2, 3, 4...
            stop_data['stop_number'] = new_number
            if old_number != new_number:
                print(f"RENUMBER: Stop {old_number} -> {new_number}")
        
        print(f"RENUMBER: After - stops: {[s['stop_number'] for s in final_stops_data]}")
        
        # Create complete tour with flag coordination
        try:
            new_tour_info = create_complete_tour(tour_path, final_stops_data, tour_id)
        except Exception as tour_e:
            error_str = str(tour_e)
            # Check if it's a JSON error from audio conversion
            if error_str.startswith('{'):
                try:
                    error_data = json.loads(error_str)
                    # REQ-024: Ensure proper error response format
                    if "status" not in error_data:
                        error_data["status"] = "error"
                    if "recoverable" not in error_data:
                        error_data["recoverable"] = True
                    return jsonify(error_data), 400
                except json.JSONDecodeError:
                    pass
            # Regular error handling
            return jsonify({"status": "error", "message": str(tour_e)}), 500
        
        # REQ-024: Proper success message with descriptive content
        custom_audio_count = sum(1 for stop in response_stops if stop.get('audio_source') == 'user_recorded')
        tts_count = len(response_stops) - custom_audio_count
        
        if custom_audio_count > 0:
            message = f"Tour updated successfully with {custom_audio_count} custom audio recording(s) and {tts_count} text-to-speech audio(s)"
        else:
            message = f"Tour updated successfully with {tts_count} text-to-speech audio file(s)"
        
        response = {
            "status": "success",
            "message": message,  # REQ-024: Never null
            "stops": response_stops,
            "new_tour_id": new_tour_info['new_tour_id'],
            "download_url": f"/tour/{new_tour_info['new_tour_id']}/download"
        }
        
        print(f"\n==== REQ-022/023 DEBUG: SENDING RESPONSE ====")
        print(f"Response stops: {len(response_stops)}")
        print(f"New tour ID: {new_tour_info['new_tour_id']}")
        for stop in response_stops:
            print(f"Response stop {stop['stop_number']}: audio_source={stop['audio_source']}, has_custom_audio={stop.get('has_custom_audio', False)}")
        
        return jsonify(response)
        
    except Exception as e:
        print(f"REQ-022/023 Error: {e}")
        # REQ-024: Proper error response with classification
        error_message = str(e)
        
        # Classify error types for better user experience
        if "database" in error_message.lower() or "connection" in error_message.lower():
            return jsonify({
                "status": "error",
                "message": "Database connection error occurred during tour save",
                "error_code": "DATABASE_ERROR",
                "recoverable": True,
                "suggested_action": "Please try again in a few moments"
            }), 500
        elif "file" in error_message.lower() or "permission" in error_message.lower():
            return jsonify({
                "status": "error",
                "message": "File system error occurred during tour processing",
                "error_code": "FILE_SYSTEM_ERROR",
                "recoverable": True,
                "suggested_action": "Please try again or contact support if problem persists"
            }), 500
        elif "timeout" in error_message.lower() or "network" in error_message.lower():
            return jsonify({
                "status": "error",
                "message": "Network timeout during tour processing",
                "error_code": "NETWORK_TIMEOUT",
                "recoverable": True,
                "suggested_action": "Check internet connection and try again"
            }), 500
        else:
            return jsonify({
                "status": "error",
                "message": f"Tour processing failed: {error_message}",
                "error_code": "PROCESSING_ERROR",
                "recoverable": True,
                "suggested_action": "Please try again or contact support with error details"
            }), 500

@app.route('/tour/<tour_id>/update-multiple-stops', methods=['POST'])
def update_multiple_stops(tour_id):
    """Legacy endpoint - redirects to bulk-save for backward compatibility"""
    return bulk_save_stops(tour_id)



@app.route('/tour/<tour_id>/edit-info', methods=['GET'])
def get_edit_info(tour_id):
    tour_path = resolve_tour_to_directory(tour_id)
    if not tour_path:
        # REQ-024: Proper not found error response
        return jsonify({
            "status": "error",
            "message": f"Tour with ID '{tour_id}' could not be found for editing",
            "error_code": "TOUR_NOT_FOUND",
            "recoverable": False,
            "suggested_action": "Please verify the tour ID and try again, or contact support"
        }), 404
    
    stops = []
    text_files = sorted(tour_path.glob("audio_*.txt"), key=lambda x: int(x.stem.split('_')[1]))
    
    for text_file in text_files:
        stop_number = int(text_file.stem.split('_')[1])
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read().strip()
            
            # Check audio source
            audio_source = "tts_generated"
            if has_custom_audio(tour_id, stop_number):
                audio_source = "user_recorded"
            
            stops.append({
                "stop_number": stop_number,
                "text_content": text_content,
                "audio_file": f"audio_{stop_number}.mp3",
                "generate_audio_from_text": True,  # Default for existing tours
                "audio_source": audio_source,
                "editable": True
            })
        except Exception as e:
            print(f"Error reading {text_file}: {e}")
    
    return jsonify({
        "tour_id": tour_id,
        "tour_name": tour_id.replace('_', ' ').title(),
        "stops": stops
    })

@app.route('/tour/<tour_id>/download', methods=['GET'])
def download_tour_with_flags(tour_id):
    """REQ-020: Enhanced download with flag information"""
    tour_path = resolve_tour_to_directory(tour_id)
    if not tour_path:
        # REQ-024: Proper not found error response
        return jsonify({
            "status": "error",
            "message": f"Tour with ID '{tour_id}' could not be found for download",
            "error_code": "TOUR_NOT_FOUND",
            "recoverable": False,
            "suggested_action": "Please verify the tour ID and try again, or contact support"
        }), 404
    
    # Check if this is a JSON request (mobile app) or file download request
    if request.headers.get('Accept') == 'application/json':
        # Return JSON with flag information
        stops = []
        text_files = sorted(tour_path.glob("audio_*.txt"), key=lambda x: int(x.stem.split('_')[1]))
        
        for text_file in text_files:
            stop_number = int(text_file.stem.split('_')[1])
            try:
                with open(text_file, 'r', encoding='utf-8') as f:
                    text_content = f.read().strip()
                
                # Check audio source
                audio_source = "tts_generated"
                if has_custom_audio(tour_id, stop_number):
                    audio_source = "user_recorded"
                
                stops.append({
                    "stop_number": stop_number,
                    "text": text_content,
                    "generate_audio_from_text": audio_source == "tts_generated",
                    "audio_source": audio_source
                })
            except Exception as e:
                print(f"Error reading {text_file}: {e}")
        
        return jsonify({
            "tour_id": tour_id,
            "stops": stops
        })
    
    # File download (existing functionality)
    zip_path = Path(TOURS_DIR) / f"{tour_path.name}.zip"
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in tour_path.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(tour_path)
                    zipf.write(file_path, arcname)
    
    return send_file(str(zip_path), as_attachment=True, download_name=f"{tour_path.name}.zip")

if __name__ == '__main__':
    os.makedirs(TOURS_DIR, exist_ok=True)
    print(f"Starting Phase 2 Tour Editing Service v{SERVICE_VERSION}")
    app.run(host='0.0.0.0', port=5022, debug=False)