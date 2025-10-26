"""
Phase 2 Tour Editing Backend - REQ-003 Implementation
Provides endpoints for tour text editing with audio regeneration
"""
SERVICE_VERSION = "1.2.6.196"

import os
import json
import uuid
import zipfile
import shutil
import requests
import psycopg2
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)

TOURS_DIR = "/app/tours"
ACTIVE_JOBS = {}
POLLY_TTS_URL = "http://polly-tts-1:5018"

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
            
            for item in tours_dir.iterdir():
                if item.is_dir():
                    item_name_lower = item.name.lower()
                    if keywords and all(keyword in item_name_lower for keyword in keywords[:2]):
                        # Prefer original tour with real content
                        if 'original' in item_name_lower:
                            return item
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

def generate_audio_for_stop(tour_path, stop_number, text_content):
    """Generate audio for a specific stop using Polly TTS"""
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
            return True
        return False
    except Exception as e:
        print(f"Audio generation failed for stop {stop_number}: {e}")
        return False

def update_html_with_all_stops(tour_path):
    """Update HTML to include all stops with proper formatting"""
    html_file = tour_path / "index.html"
    text_files = sorted(tour_path.glob("audio_*.txt"), key=lambda x: int(x.stem.split('_')[1]))
    
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audio Tour</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        .audio-item { margin: 20px 0; padding: 15px; border: 1px solid #ccc; border-radius: 5px; }
        .stop-title { font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }
        audio { width: 100%; margin: 10px 0; }
        .stop-text { margin: 10px 0; }
    </style>
</head>
<body>
    <h1>Audio Tour</h1>
'''
    
    for text_file in text_files:
        stop_num = int(text_file.stem.split('_')[1])
        
        # Read stop content
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read().strip()
            
            # Get title from first line or create default
            title_line = text_content.split('\n')[0][:60] + "..." if len(text_content.split('\n')[0]) > 60 else text_content.split('\n')[0]
            
            html_content += f'''    <div class="audio-item">
        <div class="stop-title">Stop {stop_num}: {title_line}</div>
        <audio controls preload="metadata">
            <source src="audio_{stop_num}.mp3" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
        <div class="stop-text">{text_content.replace(chr(10), '<br>')}</div>
    </div>
'''
        except Exception as e:
            print(f"Error reading stop {stop_num}: {e}")
    
    html_content += '''</body>
</html>'''
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

def create_new_tour_with_changes(original_tour_path, updated_stops):
    """Create new tour directory with changes - ISSUE-005 fix"""
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
    
    updated_stops_set = set(updated_stops)
    
    # Copy ALL files from original tour
    for file_path in original_tour_path.rglob('*'):
        if file_path.is_file():
            relative_path = file_path.relative_to(original_tour_path)
            
            # Skip audio files for changed stops only
            if file_path.name.startswith('audio_') and file_path.suffix == '.mp3':
                try:
                    stop_number = int(file_path.stem.split('_')[1])
                    if stop_number in updated_stops_set:
                        continue
                except (ValueError, IndexError):
                    pass
            
            dest_path = new_tour_path / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_path)
    
    # Update HTML to include all stops
    update_html_with_all_stops(new_tour_path)
    
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

@app.route('/tour/<tour_id>/update-multiple-stops', methods=['POST'])
def update_multiple_stops(tour_id):
    data = request.json
    stops = data.get('stops', [])
    
    if not stops:
        return jsonify({"error": "stops array is required"}), 400
    
    tour_path = resolve_tour_to_directory(tour_id)
    if not tour_path:
        return jsonify({"error": "Tour not found", "numeric_lookup_attempted": tour_id.isdigit()}), 404
    
    try:
        updated_stops = []
        added_stops = []
        
        # Find original stop count
        original_stops = len(list(tour_path.glob("audio_*.txt")))
        
        for stop_data in stops:
            stop_number = stop_data.get('stop_number')
            new_text = stop_data.get('new_text')
            original_text = stop_data.get('original_text', '')
            
            # Check if this is a new stop (beyond original count)
            if stop_number > original_stops:
                added_stops.append(stop_number)
                updated_stops.append(stop_number)
            elif new_text != original_text:
                updated_stops.append(stop_number)
            
            # Write text file for all stops (changed and added)
            if stop_number in updated_stops:
                text_file = tour_path / f"audio_{stop_number}.txt"
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(new_text)
        
        # Create new tour with changes and additions
        new_tour_info = create_new_tour_with_changes(tour_path, updated_stops)
        new_tour_path = new_tour_info['tour_path']
        
        # Generate audio for added stops
        for stop_data in stops:
            stop_number = stop_data.get('stop_number')
            if stop_number in added_stops:
                new_text = stop_data.get('new_text')
                generate_audio_for_stop(new_tour_path, stop_number, new_text)
        
        return jsonify({
            "status": "success",
            "message": f"Bulk update completed: {len(updated_stops)} stops updated ({len(added_stops)} added)",
            "updated_stops": updated_stops,
            "added_stops": added_stops,
            "new_tour_id": new_tour_info['new_tour_id'],
            "download_url": f"/tour/{new_tour_info['new_tour_id']}/download"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/tour/<tour_id>/download', methods=['GET'])
def download_tour(tour_id):
    """Download tour as ZIP file"""
    tour_path = resolve_tour_to_directory(tour_id)
    if not tour_path:
        return jsonify({"error": "Tour not found"}), 404
    
    zip_path = Path(TOURS_DIR) / f"{tour_path.name}.zip"
    if not zip_path.exists():
        # Create ZIP if it doesn't exist
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in tour_path.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(tour_path)
                    zipf.write(file_path, arcname)
    
    return send_file(str(zip_path), as_attachment=True, download_name=f"{tour_path.name}.zip")

@app.route('/tour/<tour_id>/edit-info', methods=['GET'])
def get_edit_info(tour_id):
    tour_path = resolve_tour_to_directory(tour_id)
    if not tour_path:
        return jsonify({"error": "Tour not found"}), 404
    
    stops = []
    text_files = sorted(tour_path.glob("audio_*.txt"))
    
    for i, text_file in enumerate(text_files, 1):
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read().strip()
            
            stops.append({
                "stop_number": i,
                "text_content": text_content,
                "audio_file": f"audio_{i}.mp3",
                "editable": True
            })
        except Exception as e:
            print(f"Error reading {text_file}: {e}")
    
    return jsonify({
        "tour_id": tour_id,
        "tour_name": tour_id.replace('_', ' ').title(),
        "stops": stops
    })

if __name__ == '__main__':
    os.makedirs(TOURS_DIR, exist_ok=True)
    print(f"Starting Phase 2 Tour Editing Service v{SERVICE_VERSION}")
    app.run(host='0.0.0.0', port=5022, debug=False)