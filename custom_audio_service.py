"""
Custom Audio Recording Service - REQ-018
Handles user-recorded audio uploads and version management
"""
SERVICE_VERSION = "1.0.0"

import os
import json
import uuid
import shutil
import psycopg2
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

TOURS_DIR = "/app/tours"
CUSTOM_AUDIO_DIR = "/app/custom_audio"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DURATION = 300  # 5 minutes in seconds
MAX_VERSIONS_PER_USER = 4

def get_db_connection():
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours",
        user="admin",
        password="password123"
    )

def init_database():
    """Initialize custom audio tables"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create custom_audio_files table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_audio_files (
            id SERIAL PRIMARY KEY,
            tour_id VARCHAR(255) NOT NULL,
            stop_number INTEGER NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            version_number INTEGER DEFAULT 1,
            file_path VARCHAR(500) NOT NULL,
            file_size INTEGER NOT NULL,
            duration_seconds INTEGER,
            upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            likes_count INTEGER DEFAULT 0,
            downloads_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            UNIQUE(tour_id, stop_number, user_id, version_number)
        )
    """)
    
    # Create tour_versions table for version tracking
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tour_versions (
            id SERIAL PRIMARY KEY,
            base_tour_id VARCHAR(255) NOT NULL,
            version_tour_id VARCHAR(255) NOT NULL UNIQUE,
            creator_user_id VARCHAR(255) NOT NULL,
            modification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_duration INTEGER,
            downloads_count INTEGER DEFAULT 0,
            likes_count INTEGER DEFAULT 0,
            custom_stops_count INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def sanitize_filename(filename):
    """Sanitize filename for security"""
    return secure_filename(filename).replace(' ', '_')

def get_user_id_from_request():
    """Extract user ID from request headers"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        user_id = request.form.get('user_id')
    if not user_id:
        user_id = request.json.get('user_id') if request.is_json else None
    return user_id

@app.route('/tour/<tour_id>/stop/<int:stop_number>/custom-audio', methods=['POST'])
def upload_custom_audio(tour_id, stop_number):
    """Upload custom audio for a specific stop"""
    user_id = get_user_id_from_request()
    if not user_id:
        return jsonify({"error": "User ID required"}), 400
    
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Validate file size
    audio_file.seek(0, os.SEEK_END)
    file_size = audio_file.tell()
    audio_file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"File too large. Max size: {MAX_FILE_SIZE/1024/1024}MB"}), 400
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get next version number for this user/stop
        cur.execute("""
            SELECT COALESCE(MAX(version_number), 0) + 1 
            FROM custom_audio_files 
            WHERE tour_id = %s AND stop_number = %s AND user_id = %s
        """, (tour_id, stop_number, user_id))
        version_number = cur.fetchone()[0]
        
        # Check if we need to delete old versions (keep max 4)
        cur.execute("""
            SELECT id, file_path FROM custom_audio_files 
            WHERE tour_id = %s AND stop_number = %s AND user_id = %s 
            ORDER BY version_number DESC OFFSET %s
        """, (tour_id, stop_number, user_id, MAX_VERSIONS_PER_USER - 1))
        
        old_versions = cur.fetchall()
        for old_id, old_path in old_versions:
            # Delete old file
            if os.path.exists(old_path):
                os.remove(old_path)
            # Delete database record
            cur.execute("DELETE FROM custom_audio_files WHERE id = %s", (old_id,))
        
        # Create custom audio directory
        custom_dir = Path(CUSTOM_AUDIO_DIR) / tour_id
        custom_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        filename = f"audio_{stop_number}_{user_id}_v{version_number}.mp3"
        file_path = custom_dir / filename
        
        # Save file
        audio_file.save(str(file_path))
        
        # Insert database record
        cur.execute("""
            INSERT INTO custom_audio_files 
            (tour_id, stop_number, user_id, version_number, file_path, file_size)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (tour_id, stop_number, user_id, version_number, str(file_path), file_size))
        
        custom_audio_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "custom_audio_id": custom_audio_id,
            "version": version_number,
            "file_path": str(file_path),
            "message": "Custom audio uploaded successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tour/<tour_id>/stop/<int:stop_number>/custom-audio', methods=['DELETE'])
def remove_custom_audio(tour_id, stop_number):
    """Remove custom audio for a specific stop"""
    user_id = get_user_id_from_request()
    if not user_id:
        return jsonify({"error": "User ID required"}), 400
    
    version = request.args.get('version', type=int)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if version:
            # Remove specific version
            cur.execute("""
                SELECT file_path FROM custom_audio_files 
                WHERE tour_id = %s AND stop_number = %s AND user_id = %s AND version_number = %s
            """, (tour_id, stop_number, user_id, version))
        else:
            # Remove all versions for this user/stop
            cur.execute("""
                SELECT file_path FROM custom_audio_files 
                WHERE tour_id = %s AND stop_number = %s AND user_id = %s
            """, (tour_id, stop_number, user_id))
        
        files_to_delete = cur.fetchall()
        
        # Delete files and database records
        for (file_path,) in files_to_delete:
            if os.path.exists(file_path):
                os.remove(file_path)
        
        if version:
            cur.execute("""
                DELETE FROM custom_audio_files 
                WHERE tour_id = %s AND stop_number = %s AND user_id = %s AND version_number = %s
            """, (tour_id, stop_number, user_id, version))
        else:
            cur.execute("""
                DELETE FROM custom_audio_files 
                WHERE tour_id = %s AND stop_number = %s AND user_id = %s
            """, (tour_id, stop_number, user_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": "Custom audio removed successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tour/<tour_id>/stop/<int:stop_number>/audio-versions', methods=['GET'])
def get_audio_versions(tour_id, stop_number):
    """Get all available audio versions for a stop"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT user_id, version_number, file_size, upload_timestamp, 
                   likes_count, downloads_count, duration_seconds
            FROM custom_audio_files 
            WHERE tour_id = %s AND stop_number = %s AND is_active = true
            ORDER BY likes_count DESC, upload_timestamp DESC
        """, (tour_id, stop_number))
        
        versions = []
        for row in cur.fetchall():
            versions.append({
                "user_id": row[0],
                "version": row[1],
                "file_size": row[2],
                "upload_date": row[3].isoformat(),
                "likes": row[4],
                "downloads": row[5],
                "duration": row[6]
            })
        
        cur.close()
        conn.close()
        
        return jsonify({
            "tour_id": tour_id,
            "stop_number": stop_number,
            "versions": versions,
            "has_tts_fallback": True
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tour/<tour_id>/audio-metadata', methods=['GET'])
def get_tour_audio_metadata(tour_id):
    """Get audio metadata for entire tour"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get custom audio info for all stops
        cur.execute("""
            SELECT stop_number, user_id, version_number, likes_count, upload_timestamp
            FROM custom_audio_files 
            WHERE tour_id = %s AND is_active = true
            ORDER BY stop_number, likes_count DESC
        """, (tour_id,))
        
        stops_metadata = {}
        for row in cur.fetchall():
            stop_num = row[0]
            if stop_num not in stops_metadata:
                stops_metadata[stop_num] = {
                    "has_custom_audio": True,
                    "best_version": {
                        "user_id": row[1],
                        "version": row[2],
                        "likes": row[3],
                        "upload_date": row[4].isoformat()
                    }
                }
        
        cur.close()
        conn.close()
        
        return jsonify({
            "tour_id": tour_id,
            "stops_metadata": stops_metadata
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "custom_audio", "version": SERVICE_VERSION})

if __name__ == '__main__':
    os.makedirs(CUSTOM_AUDIO_DIR, exist_ok=True)
    init_database()
    print(f"Starting Custom Audio Service v{SERVICE_VERSION}")
    app.run(host='0.0.0.0', port=5023, debug=False)