#!/usr/bin/env python3
"""
Script to extend the existing map-delivery service with tour delivery endpoints
"""
import re

def main():
    print("Extending existing map-delivery service with tour delivery endpoints...")
    
    try:
        # Read the existing map delivery service file
        with open("map_delivery_service.py", "r") as f:
            content = f.read()
        
        # Create backup
        with open("map_delivery_service.py.bak", "w") as f:
            f.write(content)
        
        # Check if tour delivery endpoints already exist
        if "/tours-near/" in content:
            print("Tour delivery endpoints already exist in map_delivery_service.py")
            return
        
        # Add required imports if not present
        imports_to_add = []
        
        if "from io import BytesIO" not in content:
            imports_to_add.append("from io import BytesIO")
        
        if "import math" not in content:
            imports_to_add.append("import math")
        
        if "send_file" not in content:
            # Update the Flask import to include send_file
            content = content.replace(
                "from flask import Flask, request, jsonify",
                "from flask import Flask, request, jsonify, send_file"
            )
        
        # Add new imports at the top
        if imports_to_add:
            import_section = "\n".join(imports_to_add) + "\n"
            # Find the first import and add before it
            first_import = re.search(r"^import ", content, re.MULTILINE)
            if first_import:
                content = content[:first_import.start()] + import_section + content[first_import.start():]
        
        # Add tour delivery functions before the existing routes
        tour_delivery_code = '''
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
            'has_audio': True  # Since we only return tours with audio data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

'''
        
        # Find where to insert the new code (before existing routes)
        first_route = re.search(r"@app\.route\(", content)
        if first_route:
            insert_pos = first_route.start()
            content = content[:insert_pos] + tour_delivery_code + "\n" + content[insert_pos:]
        else:
            # If no routes found, add at the end before if __name__ == '__main__'
            main_check = re.search(r"if __name__ == '__main__':", content)
            if main_check:
                insert_pos = main_check.start()
                content = content[:insert_pos] + tour_delivery_code + "\n" + content[insert_pos:]
            else:
                # Add at the end
                content += tour_delivery_code
        
        # Write the updated file
        with open("map_delivery_service.py", "w") as f:
            f.write(content)
        
        print("Successfully extended map_delivery_service.py with tour delivery endpoints")
        print("Added endpoints:")
        print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location")
        print("  GET /download-tour/<tour_id> - Download tour zip file")
        print("  GET /tour-info/<tour_id> - Get tour information")
        
    except FileNotFoundError:
        print("Error: map_delivery_service.py not found.")
        print("Please run check_map_delivery_service.bat first to copy the file from the container.")
    except Exception as e:
        print(f"Error extending map_delivery_service.py: {e}")

if __name__ == "__main__":
    main()