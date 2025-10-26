#!/usr/bin/env python3
"""
Map Delivery Service - Serves map data and tours from PostgreSQL database
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
import re
import psycopg2
import math
import traceback
from io import BytesIO
from datetime import datetime

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
sys.stdout.flush()

# Log all incoming requests
@app.before_request
def log_request():
    \1\nsys.stdout.flush()
    \1\nsys.stdout.flush()
    \1\nsys.stdout.flush()
    \1\nsys.stdout.flush()
    \1\nsys.stdout.flush()
    sys.stdout.flush()
app = Flask(__name__)
CORS(app)

def get_db_connection():
    """Get a connection to the database."""
    return psycopg2.connect(
        host="postgres-2",
        port=5432,
        database="audiotours",
        user="admin",
        password="password123"
    )

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy", 
        "service": "map_delivery",
        "description": "Map data and nearby tours service"
    })

@app.route('/nearby-tours', methods=['GET'])
def nearby_tours():
    """Get tours near a location within a radius."""
    try:
        # Get parameters
        lat = float(request.args.get('lat', 42.3601))  # Default to Boston
        lng = float(request.args.get('lng', -71.0589))
        radius = float(request.args.get('radius', 10.0))  # Default 10 miles
        
        # Convert miles to degrees (approximate)
        # 1 degree of latitude = ~69 miles
        # 1 degree of longitude = ~55 miles at Boston's latitude
        lat_radius = radius / 69.0
        lng_radius = radius / (math.cos(math.radians(lat)) * 69.0)
        
        # Query database for tours within radius
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = """
        SELECT id, tour_name, request_string, lat, lng, created_at
        FROM audio_tours
        WHERE lat IS NOT NULL AND lng IS NOT NULL
          AND lat BETWEEN %s AND %s
          AND lng BETWEEN %s AND %s
        ORDER BY created_at DESC
        """
        
        cur.execute(
            query,
            (lat - lat_radius, lat + lat_radius, lng - lng_radius, lng + lng_radius)
        )
        
        tours = []
        for row in cur.fetchall():
            tour_id, tour_name, request_string, tour_lat, tour_lng, created_at = row
            
            # Calculate actual distance in miles
            dlat = math.radians(tour_lat - lat)
            dlng = math.radians(tour_lng - lng)
            a = (math.sin(dlat/2) * math.sin(dlat/2) + 
                 math.cos(math.radians(lat)) * math.cos(math.radians(tour_lat)) * 
                 math.sin(dlng/2) * math.sin(dlng/2))
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = 3959 * c  # Earth radius in miles
            
            # Only include tours within the actual radius
            if distance <= radius:
                tours.append({
                    "id": tour_id,
                    "title": tour_name,
                    "request_string": request_string,
                    "lat": tour_lat,
                    "lng": tour_lng,
                    "distance": round(distance, 2),
                    "created": created_at.isoformat() if created_at else None,
                    "path": f"/tours/{tour_id}"  # Path to tour files
                })
        
        cur.close()
        conn.close()
        
        return jsonify({
            "center": {"lat": lat, "lng": lng},
            "radius": radius,
            "tours": tours
        })
        
    except Exception as e:
        \1\nsys.stdout.flush()
        return jsonify({"error": str(e)}), 500


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
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat / 2) * math.sin(delta_lat / 2) +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lng / 2) * math.sin(delta_lng / 2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    
    return distance

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
        print(f"Traceback: {traceback.format_exc()}")
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
            print(f"Tour {tour_id} not found or no audio data")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found or no audio data available'}), 404
        
        tour_name, audio_tour_data, request_string = result
        
        # Update download count
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
        
        print(f"Sending tour file: {filename} ({len(audio_tour_data)} bytes)")
        sys.stdout.flush()
        
        return send_file(
            BytesIO(audio_tour_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"ERROR in download_tour: {e}")
        print(f"Traceback: {traceback.format_exc()}")
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
        
        tour_info = {
            'id': tour_id,
            'name': tour_name,
            'request_string': request_string,
            'lat': lat,
            'lng': lng,
            'downloads': requests,
            'has_audio': True
        }
        
        print(f"Returning tour info: {tour_info}")
        sys.stdout.flush()
        
        return jsonify(tour_info)
        
    except Exception as e:
        print(f"ERROR in get_tour_info: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    ensure_tours_directory()
    
    print(f"Starting Map Delivery Service: {datetime.now().isoformat()}")
    sys.stdout.flush()
    app.run(host='0.0.0.0', port=5005, debug=True)