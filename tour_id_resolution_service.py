"""
Tour ID Resolution Service - REQ-004 Implementation
Maps download IDs (numeric) to edit IDs (UUID) for cross-service compatibility
"""
SERVICE_VERSION = "1.0.0"

import os
import json
import psycopg2
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TOURS_DIR = "/app/tours"

def get_db_connection():
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def find_edit_tour_id(download_id):
    """Find UUID-based edit tour ID from numeric download ID"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get tour info from database
        cur.execute("SELECT tour_name FROM audio_tours WHERE id = %s", (int(download_id),))
        result = cur.fetchone()
        
        if not result:
            return None
            
        tour_name = result[0].lower()
        cur.close()
        conn.close()
        
        # Find matching UUID directory
        tours_dir = Path(TOURS_DIR)
        
        # Create search keywords from tour name
        keywords = []
        if 'boston' in tour_name and 'common' in tour_name:
            keywords = ['boston', 'common']
        elif 'harvard' in tour_name:
            keywords = ['harvard', 'university']
        elif 'clark' in tour_name:
            keywords = ['clark', 'art']
        elif 'american' in tour_name and 'wing' in tour_name:
            keywords = ['american', 'wing', 'mfa']
        else:
            # Generic keyword extraction
            words = tour_name.replace(',', ' ').replace('-', ' ').split()
            keywords = [w for w in words if len(w) > 3][:3]
        
        # Find matching directory with UUID
        for item in tours_dir.iterdir():
            if item.is_dir():
                item_name_lower = item.name.lower()
                # Check if directory matches keywords and has UUID pattern
                if keywords and all(keyword in item_name_lower for keyword in keywords[:2]):
                    # Extract UUID from directory name (last part after underscore)
                    parts = item.name.split('_')
                    if len(parts) > 1:
                        uuid_part = parts[-1]
                        # Check if it looks like UUID (8+ chars, alphanumeric)
                        if len(uuid_part) >= 8 and uuid_part.replace('-', '').isalnum():
                            return {
                                'edit_tour_id': uuid_part,
                                'directory_name': item.name,
                                'full_path': str(item)
                            }
        
        return None
        
    except Exception as e:
        print(f"Error finding edit tour ID for {download_id}: {e}")
        return None

def check_tour_editability(tour_path):
    """Check if tour has separate audio files (editable format)"""
    try:
        tour_dir = Path(tour_path)
        if not tour_dir.exists():
            return False
            
        # Check for separate audio files (new format)
        audio_files = list(tour_dir.glob("audio_*.mp3"))
        text_files = list(tour_dir.glob("audio_*.txt"))
        
        # Editable if has separate audio and text files
        return len(audio_files) > 0 and len(text_files) > 0
        
    except Exception:
        return False

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy", 
        "service": "tour_id_resolution", 
        "version": SERVICE_VERSION
    })

@app.route('/tour/<download_id>/resolve', methods=['GET'])
def resolve_tour_id(download_id):
    """REQ-004: Resolve download ID to edit-compatible tour ID"""
    try:
        # Validate download ID
        if not download_id.isdigit():
            return jsonify({
                "status": "error",
                "error_code": "INVALID_DOWNLOAD_ID",
                "message": f"Download ID '{download_id}' must be numeric",
                "download_id": download_id
            }), 400
        
        # Get tour info from database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tour_name FROM audio_tours WHERE id = %s", (int(download_id),))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if not result:
            return jsonify({
                "status": "error",
                "error_code": "TOUR_NOT_FOUND",
                "message": f"Tour with download ID '{download_id}' not found",
                "download_id": int(download_id)
            }), 404
        
        tour_name = result[0]
        
        # Find corresponding edit tour ID
        edit_info = find_edit_tour_id(download_id)
        
        if not edit_info:
            return jsonify({
                "status": "error",
                "error_code": "EDIT_ID_NOT_FOUND",
                "message": f"No edit-compatible tour found for download ID '{download_id}'",
                "download_id": int(download_id),
                "tour_name": tour_name
            }), 404
        
        # Check editability
        is_editable = check_tour_editability(edit_info['full_path'])
        
        return jsonify({
            "status": "success",
            "download_id": int(download_id),
            "edit_tour_id": edit_info['edit_tour_id'],
            "tour_name": tour_name,
            "editable": is_editable,
            "has_separate_audio_files": is_editable,
            "download_url": f"/tour/{download_id}/download",
            "directory_name": edit_info['directory_name']
        })
        
    except ValueError:
        return jsonify({
            "status": "error",
            "error_code": "INVALID_DOWNLOAD_ID",
            "message": f"Download ID '{download_id}' must be numeric",
            "download_id": download_id
        }), 400
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"Failed to resolve tour ID: {str(e)}",
            "download_id": download_id
        }), 500

@app.route('/tour/<download_id>/info', methods=['GET'])
def get_tour_info(download_id):
    """Get detailed tour information for mobile app"""
    try:
        # Get basic resolution first
        resolution_response = resolve_tour_id(download_id)
        
        if resolution_response[1] != 200:  # If resolution failed
            return resolution_response
            
        resolution_data = resolution_response[0].get_json()
        
        # Add additional info
        edit_info = find_edit_tour_id(download_id)
        if edit_info:
            tour_dir = Path(edit_info['full_path'])
            
            # Count stops
            audio_files = list(tour_dir.glob("audio_*.mp3"))
            stop_count = len(audio_files)
            
            # Get file sizes
            total_size = sum(f.stat().st_size for f in tour_dir.rglob('*') if f.is_file())
            
            resolution_data.update({
                "stop_count": stop_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "last_modified": max(f.stat().st_mtime for f in tour_dir.rglob('*') if f.is_file())
            })
        
        return jsonify(resolution_data)
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error_code": "INFO_ERROR",
            "message": f"Failed to get tour info: {str(e)}",
            "download_id": download_id
        }), 500

if __name__ == '__main__':
    print(f"Starting Tour ID Resolution Service v{SERVICE_VERSION}")
    print(f"Tours directory: {TOURS_DIR}")
    app.run(host='0.0.0.0', port=5025, debug=False)