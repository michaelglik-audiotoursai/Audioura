#!/usr/bin/env python3
"""
Treats Service - Serves treats data from PostgreSQL database
"""
import os
import sys
import json
import psycopg2
import math
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\n==== TREATS SERVICE STARTING: {datetime.now().isoformat()} ====")
sys.stdout.flush()

app = Flask(__name__)
CORS(app)

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host="postgres-2",
        port="5432",
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
    return jsonify({"status": "healthy", "service": "treats"})

@app.route('/treats-near/<float:lat>/<float:lng>', methods=['GET'])
@app.route('/treats-near/<lat>/<lng>', methods=['GET'])
def get_treats_near_location(lat, lng):
    """Get 5 treats near a specific location"""
    try:
        lat = float(lat)
        lng = float(lng)
    except ValueError:
        return jsonify({'error': 'Invalid coordinates'}), 400
        
    print(f"Getting treats near lat={lat}, lng={lng}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, ad_name, ad_text, lat, lng, link_to_vendor, ad_image, distance_in_feet
            FROM treats 
            ORDER BY id DESC
        """)
        
        treats = cur.fetchall()
        treats_with_coords = []
        treats_without_coords = []
        
        for treat in treats:
            treat_id, ad_name, ad_text, treat_lat, treat_lng, link_to_vendor, ad_image, distance_in_feet = treat
            
            treat_data = {
                'id': treat_id,
                'name': ad_name,
                'description': ad_text,
                'lat': treat_lat,
                'lng': treat_lng,
                'link_to_vendor': link_to_vendor,
                'ad_image': ad_image,
                'distance_in_feet': distance_in_feet
            }
            
            if treat_lat and treat_lng:
                # Use database distance if available, otherwise calculate
                if distance_in_feet and distance_in_feet > 0:
                    treat_data['distance_km'] = round(distance_in_feet * 0.0003048, 2)  # feet to km
                else:
                    distance = calculate_distance(lat, lng, treat_lat, treat_lng)
                    treat_data['distance_km'] = round(distance, 2)
                treats_with_coords.append(treat_data)
            else:
                treats_without_coords.append(treat_data)
        
        # Sort treats with coordinates by distance
        treats_with_coords.sort(key=lambda x: x['distance_km'])
        
        # Combine: first treats with coords (sorted by distance), then without coords
        combined_treats = treats_with_coords + treats_without_coords
        
        # Take first 5
        result_treats = combined_treats[:5]
        
        cur.close()
        conn.close()
        
        print(f"Found {len(result_treats)} treats")
        sys.stdout.flush()
        
        # Add base64 encoded images to response
        for treat in result_treats:
            if treat.get('ad_image'):
                import base64
                treat['image_base64'] = base64.b64encode(treat['ad_image']).decode('utf-8')
                del treat['ad_image']  # Remove binary data
            else:
                treat['image_base64'] = None
        
        return jsonify({
            'treats': result_treats,
            'center_lat': lat,
            'center_lng': lng,
            'count': len(result_treats)
        })
        
    except Exception as e:
        print(f"ERROR in get_treats_near_location: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Treats Service...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /treats-near/<lat>/<lng> - Get 5 treats near location")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=5006, debug=True)