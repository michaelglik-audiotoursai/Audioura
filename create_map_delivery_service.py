#!/usr/bin/env python3
"""
Create a new map delivery service with tour delivery endpoints
"""

def main():
    print("Creating map delivery service with tour delivery endpoints...")
    
    service_code = '''#!/usr/bin/env python3
"""
Map Delivery Service - Serves map data and tours from PostgreSQL database
"""
import os
import sys
import json
import psycopg2
from io import BytesIO
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import math

app = Flask(__name__)
CORS(app)

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

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "map_delivery"})

@app.route('/tours-near/<float:lat>/<float:lng>', methods=['GET'])
def get_tours_near_location(lat, lng):
    """Get tours near a specific location"""
    try:
        radius_km = float(request.args.get('radius', 50))  # Default 50km radius
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all tours with coordinates
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
        
        # Sort by distance
        nearby_tours.sort(key=lambda x: x['distance_km'])
        
        cur.close()
        conn.close()
        
        return jsonify({
            'tours': nearby_tours,
            'center_lat': lat,
            'center_lng': lng,
            'radius_km': radius_km,
            'count': len(nearby_tours)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download-tour/<int:tour_id>', methods=['GET'])
def download_tour(tour_id):
    """Download a tour zip file by ID"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get tour data
        cur.execute("""
            SELECT tour_name, audio_tour, request_string
            FROM audio_tours 
            WHERE id = %s AND audio_tour IS NOT NULL
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
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
        
        # Create filename
        safe_name = request_string.replace(' ', '_').lower()
        filename = f"{safe_name}_tour.zip"
        
        # Return the zip file
        return send_file(
            BytesIO(audio_tour_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/tour-info/<int:tour_id>', methods=['GET'])
def get_tour_info(tour_id):
    """Get detailed information about a tour"""
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
        return jsonify({'error': str(e)}), 500

@app.route('/all-tours', methods=['GET'])
def get_all_tours():
    """Get all available tours"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tour_name, request_string, lat, lng, number_requested
            FROM audio_tours 
            WHERE audio_tour IS NOT NULL
            ORDER BY number_requested DESC, tour_name
        """)
        
        tours = cur.fetchall()
        
        tour_list = []
        for tour in tours:
            tour_id, tour_name, request_string, lat, lng, requests = tour
            tour_list.append({
                'id': tour_id,
                'name': tour_name,
                'request_string': request_string,
                'lat': lat,
                'lng': lng,
                'downloads': requests,
                'type': 'walking_tour'
            })
        
        cur.close()
        conn.close()
        
        return jsonify({
            'tours': tour_list,
            'count': len(tour_list)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Map Delivery Service...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location")
    print("  GET /download-tour/<tour_id> - Download tour zip file")
    print("  GET /tour-info/<tour_id> - Get tour information")
    print("  GET /all-tours - Get all available tours")
    
    app.run(host='0.0.0.0', port=5004, debug=True)
'''
    
    # Write the service file
    with open("map_delivery_service.py", "w") as f:
        f.write(service_code)
    
    print("✅ Created map_delivery_service.py")
    print("✅ Includes all endpoints needed for Flutter Map support")
    print("✅ Ready to deploy to container")

if __name__ == "__main__":
    main()