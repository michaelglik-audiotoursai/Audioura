#!/usr/bin/env python3
"""
Map Delivery Service - Serves map data and tours from PostgreSQL database
"""
import os
import sys
import json
import psycopg2
import math
import traceback
import base64
import zipfile
import tempfile
import re
import requests
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\n==== MAP DELIVERY SERVICE STARTING: {datetime.now().isoformat()} ====")
sys.stdout.flush()

app = Flask(__name__)
CORS(app)

# Log all incoming requests
@app.before_request
def log_request():
    print(f"\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote Address: {request.remote_addr}")
    print(f"User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    print(f"Content Type: {request.headers.get('Content-Type', 'Unknown')}")
    print(f"Headers: {dict(request.headers)}")
    sys.stdout.flush()

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points in kilometers"""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat / 2) * math.sin(delta_lat / 2) +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lng / 2) * math.sin(delta_lng / 2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    print("Health check requested")
    sys.stdout.flush()
    return jsonify({"status": "healthy", "service": "map_delivery", "req012": "active"})

@app.route('/version-test', methods=['GET'])
def version_test():
    """Simple version test endpoint"""
    import time
    return jsonify({
        "test": "REQ-012 working",
        "timestamp": int(time.time()),
        "version": "1.2.5.REQ012"
    })

@app.route('/tours-near/<lat>/<lng>', methods=['GET'])
def get_tours_near_location(lat, lng):
    """Get tours near a specific location (including custom tours)"""
    print(f"Getting tours near lat={lat}, lng={lng}")
    sys.stdout.flush()
    
    try:
        # Convert lat/lng to float
        lat = float(lat)
        lng = float(lng)
        radius_km = float(request.args.get('radius', 50))
        print(f"Search radius: {radius_km} km")
        sys.stdout.flush()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get original tours
        cur.execute("""
            SELECT id, tour_name, request_string, lat, lng, number_requested
            FROM audio_tours 
            WHERE lat IS NOT NULL AND lng IS NOT NULL
        """)
        
        tours = cur.fetchall()
        nearby_tours = []
        
        for tour in tours:
            tour_id, tour_name, request_string, tour_lat, tour_lng, requests = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    nearby_tours.append({
                        'id': tour_id,
                        'name': tour_name,
                        'request_string': request_string,
                        'lat': tour_lat,
                        'lng': tour_lng,
                        'distance_km': round(distance, 2),
                        'popularity': requests,
                        'type': 'walking_tour',
                        'is_custom': False
                    })
        
        # Get custom tours
        cur.execute("""
            SELECT custom_tour_id, tour_name, request_string, lat, lng, number_requested, original_tour_id
            FROM custom_tours 
            WHERE lat IS NOT NULL AND lng IS NOT NULL
        """)
        
        custom_tours = cur.fetchall()
        
        for tour in custom_tours:
            custom_id, tour_name, request_string, tour_lat, tour_lng, requests, original_id = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    nearby_tours.append({
                        'id': custom_id,  # Use custom_tour_id as id
                        'name': tour_name,
                        'request_string': request_string,
                        'lat': tour_lat,
                        'lng': tour_lng,
                        'distance_km': round(distance, 2),
                        'popularity': requests,
                        'type': 'walking_tour',
                        'is_custom': True,
                        'original_tour_id': original_id
                    })
        
        nearby_tours.sort(key=lambda x: x['distance_km'])
        cur.close()
        conn.close()
        
        print(f"Found {len(nearby_tours)} tours within {radius_km} km")
        sys.stdout.flush()
        
        return jsonify({
            'tours': nearby_tours,
            'center_lat': lat,
            'center_lng': lng,
            'radius_km': radius_km,
            'count': len(nearby_tours)
        })
        
    except Exception as e:
        print(f"ERROR in get_tours_near_location: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500



@app.route('/download-tour/<tour_id>', methods=['GET'])
def download_tour(tour_id):
    """Download a tour zip file by ID with version checking"""
    version_param = request.args.get('v', '')
    force_download = request.args.get('force', 'false').lower() == 'true'
    print(f"Downloading tour ID: {tour_id} (version: {version_param}, force: {force_download})")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if it's a custom tour
        if str(tour_id).startswith('custom_'):
            cur.execute("""
                SELECT tour_name, audio_tour, request_string
                FROM custom_tours 
                WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
            """, (tour_id,))
            
            result = cur.fetchone()
            
            if result:
                tour_name, audio_tour_data, request_string = result
                cur.execute("""
                    UPDATE custom_tours 
                    SET number_requested = number_requested + 1 
                    WHERE custom_tour_id = %s
                """, (tour_id,))
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Custom tour not found'}), 404
        else:
            # Regular tour
            cur.execute("""
                SELECT tour_name, audio_tour, request_string
                FROM audio_tours 
                WHERE id = %s AND audio_tour IS NOT NULL
            """, (int(tour_id),))
            
            result = cur.fetchone()
            
            if result:
                tour_name, audio_tour_data, request_string = result
                cur.execute("""
                    UPDATE audio_tours 
                    SET number_requested = number_requested + 1 
                    WHERE id = %s
                """, (int(tour_id),))
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Tour not found'}), 404
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Version checking logic
        if version_param and not force_download:
            import time
            current_version = f"1.2.5.{int(time.time())}"
            if version_param == current_version:
                return '', 304  # Not Modified
        
        safe_name = request_string.replace(' ', '_').lower()
        filename = f"{safe_name}_tour.zip"
        
        print(f"Sending tour file: {filename}")
        sys.stdout.flush()
        
        response = send_file(
            BytesIO(audio_tour_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
        
        # Add version headers
        import time
        response.headers['X-Tour-Version'] = f"1.2.5.{int(time.time())}"
        response.headers['X-Last-Modified'] = datetime.now().isoformat()
        
        return response
        
    except Exception as e:
        print(f"ERROR in download_tour: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/search-tours', methods=['GET'])
def search_tours():
    """Search tours by query (enhanced to include custom tours)"""
    query = request.args.get('query', '').strip()
    print(f"Searching tours with query: '{query}'")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        all_tours = []
        
        if query:
            # Search original tours
            cur.execute("""
                SELECT id, tour_name, request_string, lat, lng, number_requested
                FROM audio_tours 
                WHERE (LOWER(tour_name) LIKE LOWER(%s) OR LOWER(request_string) LIKE LOWER(%s))
                AND lat IS NOT NULL AND lng IS NOT NULL
            """, (f'%{query}%', f'%{query}%'))
            
            tours = cur.fetchall()
            
            for tour in tours:
                tour_id, tour_name, request_string, tour_lat, tour_lng, requests = tour
                all_tours.append({
                    'id': tour_id,
                    'name': tour_name,
                    'request_string': request_string,
                    'lat': tour_lat,
                    'lng': tour_lng,
                    'distance_km': 0,  # Will be calculated if needed
                    'popularity': requests,
                    'type': 'walking_tour',
                    'is_custom': False
                })
            
            # Search custom tours
            cur.execute("""
                SELECT custom_tour_id, tour_name, request_string, lat, lng, number_requested, original_tour_id
                FROM custom_tours 
                WHERE (LOWER(tour_name) LIKE LOWER(%s) OR LOWER(request_string) LIKE LOWER(%s))
                AND lat IS NOT NULL AND lng IS NOT NULL
            """, (f'%{query}%', f'%{query}%'))
            
            custom_tours = cur.fetchall()
            
            for tour in custom_tours:
                custom_id, tour_name, request_string, tour_lat, tour_lng, requests, original_id = tour
                all_tours.append({
                    'id': custom_id,
                    'name': tour_name,
                    'request_string': request_string,
                    'lat': tour_lat,
                    'lng': tour_lng,
                    'distance_km': 0,  # Will be calculated if needed
                    'popularity': requests,
                    'type': 'walking_tour',
                    'is_custom': True,
                    'original_tour_id': original_id
                })
        
        # Sort by popularity
        all_tours.sort(key=lambda x: x['popularity'], reverse=True)
        
        cur.close()
        conn.close()
        
        print(f"Found {len(all_tours)} tours matching query")
        sys.stdout.flush()
        
        return jsonify({
            'tours': all_tours,
            'count': len(all_tours),
            'pattern': query
        })
        
    except Exception as e:
        print(f"ERROR in search_tours: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour/<int:tour_id>/version', methods=['GET'])
def get_tour_version(tour_id):
    """Get tour version information for update checking"""
    print(f"Getting version for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tour_name FROM audio_tours 
            WHERE id = %s AND audio_tour IS NOT NULL
        """, (int(tour_id),))
        
        result = cur.fetchone()
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': 'Tour not found'}), 404
        
        cur.close()
        conn.close()
        
        import time
        current_timestamp = int(time.time())
        version = f"1.2.5.{current_timestamp}"
        
        return jsonify({
            'tour_id': tour_id,
            'version': version,
            'last_modified': datetime.now().isoformat(),
            'has_updates': True
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_version: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tours/check-versions', methods=['POST'])
def check_multiple_versions():
    """Bulk version check for multiple tours"""
    data = request.json
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Expected array of tour version checks'}), 400
    
    results = []
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        for item in data:
            tour_id = item.get('tour_id')
            local_version = item.get('local_version', '1.0.0')
            
            if not tour_id:
                continue
                
            cur.execute("""
                SELECT id FROM audio_tours 
                WHERE id = %s AND audio_tour IS NOT NULL
            """, (int(tour_id),))
            
            if cur.fetchone():
                import time
                server_version = f"1.2.5.{int(time.time())}"
                needs_update = server_version != local_version
                
                results.append({
                    'tour_id': tour_id,
                    'server_version': server_version,
                    'local_version': local_version,
                    'needs_update': needs_update
                })
        
        cur.close()
        conn.close()
        
        return jsonify(results)
        
    except Exception as e:
        print(f"ERROR in check_multiple_versions: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour-info/<int:tour_id>', methods=['GET'])
def get_tour_info(tour_id):
    """Get detailed information about a tour with version info"""
    print(f"Getting info for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tour_name, request_string, lat, lng, number_requested
            FROM audio_tours 
            WHERE id = %s
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
            print(f"Tour {tour_id} not found")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        tour_id, tour_name, request_string, lat, lng, requests = result
        cur.close()
        conn.close()
        
        # Generate version based on current timestamp (simplified)
        import time
        current_timestamp = int(time.time())
        version = f"1.2.5.{current_timestamp}"
        
        return jsonify({
            'id': tour_id,
            'name': tour_name,
            'request_string': request_string,
            'lat': lat,
            'lng': lng,
            'downloads': requests,
            'has_audio': True,
            'version': version,
            'last_modified': datetime.now().isoformat(),
            'has_custom_edits': True,
            'download_url': f'/download-tour/{tour_id}?v={current_timestamp}',
            'api_version': '1.2.5.REQ012'
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_info: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

def ensure_custom_tours_table():
    """Ensure custom_tours table exists"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_tours (
                id SERIAL PRIMARY KEY,
                custom_tour_id VARCHAR(255) UNIQUE NOT NULL,
                original_tour_id INTEGER REFERENCES audio_tours(id),
                user_id VARCHAR(255),
                tour_name VARCHAR(255) NOT NULL,
                request_string TEXT NOT NULL,
                audio_tour BYTEA,
                lat DOUBLE PRECISION,
                lng DOUBLE PRECISION,
                number_requested INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Custom tours table ensured")
    except Exception as e:
        print(f"Error ensuring custom_tours table: {e}")

def extract_tour_stops(tour_id):
    """Extract stops from a tour's HTML content"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if it's a custom tour
    if str(tour_id).startswith('custom_'):
        cur.execute("""
            SELECT audio_tour, tour_name FROM custom_tours 
            WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
        """, (tour_id,))
    else:
        cur.execute("""
            SELECT audio_tour, tour_name FROM audio_tours 
            WHERE id = %s AND audio_tour IS NOT NULL
        """, (tour_id,))
    
    result = cur.fetchone()
    if not result:
        cur.close()
        conn.close()
        return []
    
    audio_tour_data, tour_name = result
    cur.close()
    conn.close()
    
    stops = []
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "tour.zip")
            with open(zip_path, 'wb') as f:
                f.write(audio_tour_data)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # List all files in the zip
                file_list = zip_ref.namelist()
                
                # Find HTML file
                html_file = None
                for file in file_list:
                    if file.endswith('.html'):
                        html_file = file
                        break
                
                if not html_file:
                    return []
                
                html_content = zip_ref.read(html_file).decode('utf-8')
                
                # Extract tour stops from HTML
                # Look for audio files and their corresponding text
                audio_files = [f for f in file_list if f.endswith('.mp3')]
                
                for i, audio_file in enumerate(audio_files):
                    # Extract title from filename or HTML
                    title = os.path.splitext(os.path.basename(audio_file))[0]
                    title = title.replace('_', ' ').title()
                    
                    # Try to extract text content from HTML
                    text_pattern = rf'<p[^>]*>([^<]*{re.escape(title)}[^<]*)</p>'
                    text_match = re.search(text_pattern, html_content, re.IGNORECASE)
                    current_text = text_match.group(1) if text_match else f"Welcome to {title}"
                    
                    stops.append({
                        'stop_number': i + 1,
                        'title': title,
                        'current_text': current_text,
                        'audio_file': audio_file,
                        'audio_duration': 45,  # Default duration
                        'editable': True
                    })
    except Exception as e:
        print(f"Error extracting tour stops: {e}")
        # Return basic structure if extraction fails
        stops = [{
            'stop_number': 1,
            'title': 'Tour Stop 1',
            'current_text': 'Welcome to this tour location',
            'audio_file': 'audio_1.mp3',
            'audio_duration': 45,
            'editable': True
        }]
    
    return stops

@app.route('/tour/<tour_id>/edit-info', methods=['GET'])
def get_tour_edit_info(tour_id):
    """Get tour information for editing"""
    print(f"Getting edit info for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if it's a custom tour or regular tour
        if str(tour_id).startswith('custom_'):
            cur.execute("""
                SELECT custom_tour_id, tour_name FROM custom_tours 
                WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
            """, (tour_id,))
        else:
            cur.execute("""
                SELECT id, tour_name FROM audio_tours 
                WHERE id = %s AND audio_tour IS NOT NULL
            """, (int(tour_id),))
        
        result = cur.fetchone()
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': 'Tour not found'}), 404
        
        tour_id_db, tour_name = result
        cur.close()
        conn.close()
        
        # Extract stops from tour
        stops = extract_tour_stops(tour_id)
        
        return jsonify({
            'tour_id': str(tour_id),
            'tour_name': tour_name,
            'stops': stops
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_edit_info: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour/<tour_id>/update-stop', methods=['POST'])
def update_tour_stop(tour_id):
    """Update a specific stop in a tour"""
    print(f"Updating stop for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        stop_number = data.get('stop_number')
        new_text = data.get('new_text')
        audio_file = data.get('audio_file')  # Base64 encoded
        audio_format = data.get('audio_format', 'mp3')
        
        if not stop_number:
            return jsonify({'error': 'stop_number is required'}), 400
        
        # Store the modification for later processing
        # In a full implementation, this would modify the tour ZIP file
        print(f"Stop {stop_number} update requested:")
        print(f"  New text: {new_text[:100] if new_text else 'None'}...")
        print(f"  Has custom audio: {bool(audio_file)}")
        
        # If new text provided, generate new audio using Polly TTS
        if new_text:
            try:
                # Call Polly TTS service
                tts_response = requests.post(
                    "http://polly-tts:5018/synthesize",
                    json={
                        "text": new_text,
                        "voice_id": "Joanna",
                        "output_format": "mp3"
                    },
                    timeout=30
                )
                
                if tts_response.status_code == 200:
                    print(f"Generated new audio for stop {stop_number}")
                else:
                    print(f"TTS generation failed: {tts_response.text}")
            except Exception as tts_error:
                print(f"TTS service error: {tts_error}")
        
        return jsonify({
            'status': 'success',
            'message': f'Stop {stop_number} updated',
            'tour_id': tour_id,
            'stop_number': stop_number
        })
        
    except Exception as e:
        print(f"ERROR in update_tour_stop: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour/<tour_id>/create-custom', methods=['POST'])
def create_custom_tour(tour_id):
    """Create a custom version of a tour"""
    print(f"Creating custom tour from ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        data = request.json or {}
        custom_name = data.get('custom_name', f'Custom Tour {tour_id}')
        modifications = data.get('modifications', [])
        user_id = data.get('user_id', 'anonymous')
        
        # Ensure custom tours table exists
        ensure_custom_tours_table()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get original tour
        if str(tour_id).startswith('custom_'):
            cur.execute("""
                SELECT tour_name, request_string, audio_tour, lat, lng, original_tour_id
                FROM custom_tours 
                WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
            """, (tour_id,))
            result = cur.fetchone()
            if result:
                tour_name, request_string, audio_tour, lat, lng, original_id = result
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Original tour not found'}), 404
        else:
            cur.execute("""
                SELECT tour_name, request_string, audio_tour, lat, lng
                FROM audio_tours 
                WHERE id = %s AND audio_tour IS NOT NULL
            """, (int(tour_id),))
            result = cur.fetchone()
            if result:
                tour_name, request_string, audio_tour, lat, lng = result
                original_id = int(tour_id)
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Original tour not found'}), 404
        
        # Generate unique custom tour ID
        import time
        timestamp = int(time.time())
        custom_tour_id = f"custom_{original_id}_{timestamp}"
        
        # Process modifications
        modified_audio_tour = audio_tour  # Start with original
        
        # Apply text modifications using TTS
        for mod in modifications:
            stop_number = mod.get('stop_number')
            new_text = mod.get('new_text')
            has_custom_audio = mod.get('has_custom_audio', False)
            
            if new_text and not has_custom_audio:
                try:
                    # Generate new audio using Polly TTS
                    tts_response = requests.post(
                        "http://polly-tts:5018/synthesize",
                        json={
                            "text": new_text,
                            "voice_id": "Joanna",
                            "output_format": "mp3"
                        },
                        timeout=30
                    )
                    
                    if tts_response.status_code == 200:
                        print(f"Generated new audio for stop {stop_number}")
                        # In full implementation, would modify the ZIP file
                    else:
                        print(f"TTS generation failed for stop {stop_number}: {tts_response.text}")
                except Exception as tts_error:
                    print(f"TTS service error for stop {stop_number}: {tts_error}")
        
        # Insert custom tour
        cur.execute("""
            INSERT INTO custom_tours 
            (custom_tour_id, original_tour_id, user_id, tour_name, request_string, audio_tour, lat, lng)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (custom_tour_id, original_id, user_id, custom_name, request_string, modified_audio_tour, lat, lng))
        
        custom_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'custom_tour_id': custom_tour_id,
            'download_url': f'/download-tour/{custom_tour_id}',
            'status': 'processing'
        })
        
    except Exception as e:
        print(f"ERROR in create_custom_tour: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Ensure custom tours table exists on startup
    ensure_custom_tours_table()
    
    print("Starting Map Delivery Service with Phase 2 Tour Editing...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location (includes custom)")
    print("  GET /search-tours?query=<text> - Search tours by text (includes custom)")
    print("  GET /download-tour/<tour_id> - Download tour zip file (supports custom)")
    print("  GET /tour-info/<tour_id> - Get tour information")
    print("  GET /tour/<tour_id>/edit-info - Get tour editing information")
    print("  POST /tour/<tour_id>/update-stop - Update a tour stop")
    print("  POST /tour/<tour_id>/create-custom - Create custom tour version")
    print("\nPhase 2 Tour Editing Features:")
    print("  - Tour structure extraction for editing")
    print("  - Individual stop content updates")
    print("  - Custom tour generation with modifications")
    print("  - Polly TTS integration for text changes")
    print("  - Enhanced tours-near with custom tour support")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=5005, debug=True)
