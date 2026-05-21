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
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, send_file, make_response

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\n==== MAP DELIVERY SERVICE STARTING: {datetime.now().isoformat()} ====")
sys.stdout.flush()

app = Flask(__name__)

# CORS headers for web platform support
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.after_request
def after_request(response):
    return add_cors_headers(response)

# Handle preflight OPTIONS requests
@app.route('/health', methods=['OPTIONS'])
@app.route('/tours-near/<lat>/<lng>', methods=['OPTIONS'])
@app.route('/download-tour/<int:tour_id>', methods=['OPTIONS'])
@app.route('/tour-info/<int:tour_id>', methods=['OPTIONS'])
@app.route('/search-tours', methods=['OPTIONS'])
def handle_options(*args, **kwargs):
    response = make_response()
    return add_cors_headers(response)

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
    return jsonify({"status": "healthy", "service": "map_delivery"})

@app.route('/tours-near/<lat>/<lng>', methods=['GET'])
def get_tours_near_location(lat, lng):
    """Get tours near a specific location - all languages for map display"""
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
        
        # Get only English/original tours for map display (no translations)
        cur.execute("""
            SELECT id, tour_name, request_string, lat, lng, number_requested, content_language, original_tour_id
            FROM audio_tours 
            WHERE lat IS NOT NULL AND lng IS NOT NULL
            AND (content_language = 'en' OR content_language IS NULL)
            AND original_tour_id IS NULL
        """)
        
        tours = cur.fetchall()
        tours_list = []
        
        for tour in tours:
            tour_id, tour_name, request_string, tour_lat, tour_lng, requests, language, original_id = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    tour_data = {
                        'id': tour_id,
                        'name': tour_name,
                        'request_string': request_string,
                        'lat': tour_lat,
                        'lng': tour_lng,
                        'distance_km': round(distance, 2),
                        'popularity': requests,
                        'type': 'walking_tour',
                        'language': language or 'en',
                        'original_tour_id': original_id
                    }
                    tours_list.append(tour_data)
        
        # Sort tours by distance
        tours_list.sort(key=lambda x: x['distance_km'])
        
        cur.close()
        conn.close()
        
        print(f"Found {len(tours_list)} tours within {radius_km} km")
        sys.stdout.flush()
        
        return jsonify({
            'tours': tours_list,
            'center_lat': lat,
            'center_lng': lng,
            'radius_km': radius_km,
            'total_count': len(tours_list)
        })
        
    except Exception as e:
        print(f"ERROR in get_tours_near_location: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/download-tour/<int:tour_id>', methods=['GET'])
def download_tour(tour_id):
    """Download a tour zip file by ID with multi-language support"""
    languages = request.args.get('languages', 'en').split('|')
    user_id = request.args.get('user_id', 'anonymous')
    print(f"Downloading tour ID: {tour_id}, languages: {languages}, user: {user_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT tour_name, audio_tour, request_string
            FROM audio_tours 
            WHERE id = %s AND audio_tour IS NOT NULL
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
            print(f"Tour {tour_id} not found")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        tour_name, audio_tour_data, request_string = result
        
        cur.execute("""
            UPDATE audio_tours 
            SET number_requested = number_requested + 1 
            WHERE id = %s
        """, (tour_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        safe_name = request_string.encode('ascii', 'ignore').decode('ascii').replace(' ', '_').lower()
        if not safe_name:  # If all characters were non-ASCII
            safe_name = f"tour_{tour_id}"
        filename = f"{safe_name}_tour.zip"
        
        print(f"Sending tour file: {filename}")
        sys.stdout.flush()
        
        # Use streaming response for large files
        from flask import Response
        
        def generate():
            # Stream the file in chunks
            chunk_size = 8192  # 8KB chunks
            data = BytesIO(audio_tour_data)
            while True:
                chunk = data.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        
        return Response(
            generate(),
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(audio_tour_data)),
                'Content-Type': 'application/zip'
            }
        )
        
    except Exception as e:
        print(f"ERROR in download_tour: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour-info/<int:tour_id>', methods=['GET'])
def get_tour_info(tour_id):
    """Get detailed information about a tour"""
    print(f"Getting info for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tour_name, request_string, lat, lng, number_requested, content_language, original_tour_id
            FROM audio_tours 
            WHERE id = %s
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
            print(f"Tour {tour_id} not found")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        tour_id, tour_name, request_string, lat, lng, requests, language, original_id = result
        cur.close()
        conn.close()
        
        is_translation = original_id is not None and (language and language != 'en')
        
        return jsonify({
            'id': tour_id,
            'name': tour_name,
            'request_string': request_string,
            'lat': lat,
            'lng': lng,
            'downloads': requests,
            'has_audio': True,
            'language': language or 'en',
            'is_translation': is_translation,
            'parent_tour_id': original_id
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_info: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/search-tours', methods=['GET'])
def search_tours():
    """Search tours by pattern"""
    pattern = request.args.get('pattern', '')
    lat = float(request.args.get('lat', 0))
    lng = float(request.args.get('lng', 0))
    
    print(f"Searching tours with pattern: '{pattern}' near lat={lat}, lng={lng}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Use ILIKE for case-insensitive pattern matching
        # Convert regex pattern back to SQL LIKE pattern
        sql_pattern = pattern.replace('.*', '%')
        
        cur.execute("""
            SELECT id, tour_name, request_string, lat, lng, number_requested, content_language, original_tour_id
            FROM audio_tours 
            WHERE (tour_name ILIKE %s OR request_string ILIKE %s)
            AND lat IS NOT NULL AND lng IS NOT NULL
            ORDER BY number_requested DESC
            LIMIT 50
        """, (f'%{sql_pattern}%', f'%{sql_pattern}%'))
        
        tours = cur.fetchall()
        search_results = []
        
        for tour in tours:
            tour_id, tour_name, request_string, tour_lat, tour_lng, requests, language, original_id = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                is_translation = original_id is not None and (language and language != 'en')
                
                search_results.append({
                    'id': tour_id,
                    'name': tour_name,
                    'request_string': request_string,
                    'lat': tour_lat,
                    'lng': tour_lng,
                    'distance_km': round(distance, 2),
                    'popularity': requests,
                    'type': 'walking_tour',
                    'language': language or 'en',
                    'is_translation': is_translation,
                    'parent_tour_id': original_id
                })
        
        # Sort by popularity first, then by distance
        search_results.sort(key=lambda x: (-x['popularity'], x['distance_km']))
        
        cur.close()
        conn.close()
        
        print(f"Found {len(search_results)} tours matching pattern '{pattern}'")
        sys.stdout.flush()
        
        return jsonify({
            'tours': search_results,
            'pattern': pattern,
            'count': len(search_results)
        })
        
    except Exception as e:
        print(f"ERROR in search_tours: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Map Delivery Service...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location")
    print("  GET /download-tour/<tour_id> - Download tour zip file")
    print("  GET /tour-info/<tour_id> - Get tour information")
    print("  GET /search-tours?pattern=<pattern>&lat=<lat>&lng=<lng> - Search tours by pattern")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=5005, debug=True)
