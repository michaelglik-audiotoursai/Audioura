#!/usr/bin/env python3
"""
Script to create a clean map delivery service without regex issues
"""

def main():
    print("Creating clean map delivery service...")
    
    try:
        # Read the existing app.py file
        with open("app.py", "r") as f:
            original_content = f.read()
        
        # Create backup
        with open("app.py.bak", "w") as f:
            f.write(original_content)
        
        # Create a clean new service
        service_code = '''#!/usr/bin/env python3
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
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\\n==== MAP DELIVERY SERVICE STARTING: {datetime.now().isoformat()} ====")
sys.stdout.flush()

app = Flask(__name__)
CORS(app)

# Log all incoming requests
@app.before_request
def log_request():
    print(f"\\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote Address: {request.remote_addr}")
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

@app.route('/tours-near/<float:lat>/<float:lng>', methods=['GET'])
def get_tours_near_location(lat, lng):
    """Get tours near a specific location"""
    print(f"Getting tours near lat={lat}, lng={lng}")
    sys.stdout.flush()
    
    try:
        radius_km = float(request.args.get('radius', 50))
        print(f"Search radius: {radius_km} km")
        sys.stdout.flush()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
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
                        'type': 'walking_tour'
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

@app.route('/download-tour/<int:tour_id>', methods=['GET'])
def download_tour(tour_id):
    """Download a tour zip file by ID"""
    print(f"Downloading tour ID: {tour_id}")
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
        
        safe_name = request_string.replace(' ', '_').lower()
        filename = f"{safe_name}_tour.zip"
        
        print(f"Sending tour file: {filename}")
        sys.stdout.flush()
        
        return send_file(
            BytesIO(audio_tour_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
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
        
        return jsonify({
            'id': tour_id,
            'name': tour_name,
            'request_string': request_string,
            'lat': lat,
            'lng': lng,
            'downloads': requests,
            'has_audio': True
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_info: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Map Delivery Service...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location")
    print("  GET /download-tour/<tour_id> - Download tour zip file")
    print("  GET /tour-info/<tour_id> - Get tour information")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=5005, debug=True)
'''
        
        # Write the clean service
        with open("map_delivery_service.py", "w") as f:
            f.write(service_code)
        
        print("✅ Created clean map_delivery_service.py")
        print("✅ No regex issues")
        print("✅ Proper logging with sys.stdout.flush()")
        print("✅ All tour delivery endpoints included")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()