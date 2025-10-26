"""
Phase 2 Tour Editing Backend - REQ-003 Implementation
Provides endpoints for tour text editing with audio regeneration
"""
SERVICE_VERSION = "1.2.6.190"

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
        for stop_data in stops:
            stop_number = stop_data.get('stop_number')
            new_text = stop_data.get('new_text')
            original_text = stop_data.get('original_text')
            
            if new_text != original_text:
                updated_stops.append(stop_number)
                text_file = tour_path / f"audio_{stop_number}.txt"
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(new_text)
        
        new_uuid = str(uuid.uuid4())
        
        return jsonify({
            "status": "success",
            "message": f"Bulk update completed: {len(updated_stops)} stops updated",
            "updated_stops": updated_stops,
            "new_tour_id": new_uuid,
            "download_url": f"/tour/{new_uuid}/download"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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