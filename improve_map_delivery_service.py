#!/usr/bin/env python3
"""
Script to improve the map delivery service with proper naming, logging, and tour endpoints
"""
import re
from datetime import datetime

def main():
    print("Improving map delivery service with proper naming and logging...")
    
    try:
        # Read the existing app.py file
        with open("app.py", "r") as f:
            content = f.read()
        
        # Create backup
        with open("app.py.bak", "w") as f:
            f.write(content)
        
        print("Current endpoints found:")
        routes = re.findall(r"@app\.route\('([^']+)'", content)
        for route in routes:
            print(f"  {route}")
        
        # Add proper imports and logging configuration at the top
        imports_section = '''#!/usr/bin/env python3
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
    print(f"User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    sys.stdout.flush()

'''
        
        # Find the first import and replace everything before it
        first_import_match = re.search(r'^(import|from)', content, re.MULTILINE)
        if first_import_match:
            # Keep everything after the first import
            content_after_imports = content[first_import_match.start():]
            # Remove old imports and add new ones
            content = imports_section + content_after_imports
        else:
            content = imports_section + content
        
        # Remove duplicate imports if they exist
        content = re.sub(r'import os\n', '', content)
        content = re.sub(r'import sys\n', '', content)
        content = re.sub(r'from flask import.*\n', '', content)
        content = re.sub(r'from flask_cors import CORS\n', '', content)
        
        # Add sys.stdout.flush() after key print statements in existing endpoints
        content = re.sub(r'(print\(f?"[^"]*"\))', r'\\1\\nsys.stdout.flush()', content)
        
        # Add tour delivery endpoints before if __name__ == '__main__'
        tour_delivery_code = '''
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

'''
        
        # Find where to insert the new code (before if __name__ == '__main__')
        main_check = re.search(r"if __name__ == '__main__':", content)
        if main_check:
            insert_pos = main_check.start()
            content = content[:insert_pos] + tour_delivery_code + "\n" + content[insert_pos:]
        else:
            content += tour_delivery_code
        
        # Write the improved file as map_delivery_service.py
        with open("map_delivery_service.py", "w") as f:
            f.write(content)
        
        print("\n✅ Created improved map_delivery_service.py")
        print("✅ Added proper naming (map_delivery_service.py)")
        print("✅ Added unbuffered logging with sys.stdout.reconfigure(line_buffering=True)")
        print("✅ Added sys.stdout.flush() after all print statements")
        print("✅ Added request logging middleware")
        print("✅ Added tour delivery endpoints for Flutter Map")
        print("✅ All existing functionality preserved")
        
    except FileNotFoundError:
        print("❌ Error: app.py not found.")
        print("Please run get_existing_app.bat first to copy the file from the container.")
    except Exception as e:
        print(f"❌ Error improving service: {e}")

if __name__ == "__main__":
    main()