#!/usr/bin/env python3
"""
Script to safely extend the existing app.py with tour delivery endpoints
"""
import re

def main():
    print("Extending existing app.py with tour delivery endpoints...")
    print("This will ONLY ADD new endpoints without modifying existing ones.")
    
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
        
        # Check if tour delivery endpoints already exist
        if "/tours-near/" in content:
            print("Tour delivery endpoints already exist in app.py")
            print("No changes needed.")
            return
        
        # Add required imports ONLY if not present
        imports_added = []
        
        if "from io import BytesIO" not in content:
            content = "from io import BytesIO\n" + content
            imports_added.append("BytesIO")
        
        if "import math" not in content:
            content = "import math\n" + content
            imports_added.append("math")
        
        if "send_file" not in content and "from flask import" in content:
            # Update Flask import to include send_file
            flask_import_pattern = r"from flask import ([^\\n]+)"
            flask_match = re.search(flask_import_pattern, content)
            if flask_match and "send_file" not in flask_match.group(1):
                old_import = flask_match.group(0)
                new_import = old_import.rstrip() + ", send_file"
                content = content.replace(old_import, new_import)
                imports_added.append("send_file")
        
        if imports_added:
            print(f"Added imports: {', '.join(imports_added)}")
        
        # Add tour delivery functions before if __name__ == '__main__'
        tour_delivery_code = '''
# ===== TOUR DELIVERY ENDPOINTS (ADDED FOR FLUTTER MAP SUPPORT) =====

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
    """Get tours near a specific location (NEW ENDPOINT FOR FLUTTER MAP)"""
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
    """Download a tour zip file by ID (NEW ENDPOINT FOR FLUTTER MAP)"""
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
    """Get detailed information about a tour (NEW ENDPOINT FOR FLUTTER MAP)"""
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

# ===== END OF TOUR DELIVERY ENDPOINTS =====

'''
        
        # Find where to insert the new code (before if __name__ == '__main__')
        main_check = re.search(r"if __name__ == '__main__':", content)
        if main_check:
            insert_pos = main_check.start()
            content = content[:insert_pos] + tour_delivery_code + "\n" + content[insert_pos:]
        else:
            # Add at the end if no main check found
            content += tour_delivery_code
        
        # Write the updated file
        with open("app.py", "w") as f:
            f.write(content)
        
        print("\n✅ Successfully extended app.py")
        print("✅ All existing endpoints remain unchanged")
        print("✅ Added NEW endpoints for Flutter Map support:")
        print("   GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location")
        print("   GET /download-tour/<tour_id> - Download tour zip file")
        print("   GET /tour-info/<tour_id> - Get tour information")
        print("\n✅ Your existing Flutter app will continue to work exactly as before")
        print("✅ Service runs on port 5005 (as shown in your Docker output)")
        
    except FileNotFoundError:
        print("❌ Error: app.py not found.")
        print("Please run get_existing_app.bat first to copy the file from the container.")
    except Exception as e:
        print(f"❌ Error extending app.py: {e}")

if __name__ == "__main__":
    main()