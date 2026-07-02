"""
Tour ID Resolution Service - REQ-004 Implementation
Maps download IDs (numeric) to edit IDs (UUID) for cross-service compatibility
"""
import sys
sys.path.insert(0, '/app')  # Ensure storied modules are importable
try:
    from storied_version_constants import STORIED_SERVICE_VERSION
    SERVICE_VERSION = STORIED_SERVICE_VERSION
except ImportError:
    SERVICE_VERSION = "2.2.0.1"

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
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
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
        
        # Find matching ZIP file with UUID
        for item in tours_dir.iterdir():
            if item.is_file() and item.name.endswith('.zip'):
                item_name_lower = item.name.lower()
                # Check if file matches keywords and has UUID pattern
                if keywords and all(keyword in item_name_lower for keyword in keywords[:2]):
                    # Extract UUID from filename (last part before .zip)
                    name_without_ext = item.stem
                    parts = name_without_ext.split('_')
                    if len(parts) > 1:
                        uuid_part = parts[-1]
                        # Check if it looks like UUID (8+ chars, alphanumeric)
                        if len(uuid_part) >= 8 and uuid_part.replace('-', '').isalnum():
                            return {
                                'edit_tour_id': uuid_part,
                                'directory_name': name_without_ext,
                                'full_path': str(item)
                            }
        
        return None
        
    except Exception as e:
        print(f"Error finding edit tour ID for {download_id}: {e}")
        return None

def check_tour_editability(tour_path):
    """Check if tour ZIP file exists (simplified check)"""
    try:
        tour_file = Path(tour_path)
        # For ZIP files, just check if file exists and is reasonable size
        if tour_file.exists() and tour_file.is_file() and tour_file.suffix == '.zip':
            file_size = tour_file.stat().st_size
            # Consider editable if ZIP file is larger than 1MB (has content)
            return file_size > 1024 * 1024
        return False
        
    except Exception:
        return False

def count_mp3_files_from_zip(zip_path):
    """Count MP3 files in ZIP - only for modern tours with separate audio files"""
    try:
        import zipfile
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Count MP3 files (excluding system files)
            mp3_files = [f for f in zip_ref.namelist() 
                        if f.endswith('.mp3') and not f.startswith('__MACOSX/')]
            return len(mp3_files)
        
    except Exception as e:
        print(f"Error counting MP3 files from ZIP {zip_path}: {e}")
        return 0  # Return 0 if can't count - field will be omitted

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy", 
        "service": "tour_id_resolution", 
        "version": SERVICE_VERSION,
        "mode": os.getenv("STORIED_MODE", "false")
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
        
        # Build response
        response_data = {
            "status": "success",
            "download_id": int(download_id),
            "edit_tour_id": edit_info['edit_tour_id'],
            "tour_name": tour_name,
            "editable": is_editable,
            "has_separate_audio_files": is_editable,
            "download_url": f"/tour/{download_id}/download",
            "directory_name": edit_info['directory_name']
        }
        
        # Only add stops_count for modern tours with MP3 files
        stops_count = count_mp3_files_from_zip(edit_info['full_path'])
        if stops_count > 0:
            response_data["stops_count"] = stops_count
        
        return jsonify(response_data)
        
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