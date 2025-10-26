#!/usr/bin/env python3
"""
Script to directly modify the store_audio_tour function to call the coordinates-fromai service.
"""
import sys

def fix_store_audio_tour():
    """Fix the store_audio_tour function to call the coordinates-fromai service."""
    try:
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak_direct", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak_direct")
        
        # Replace the entire store_audio_tour function with a fixed version
        new_function = """
def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):
    """Store an audio tour in the database with coordinates and ZIP file."""
    try:
        print(f"\\n==== STORING TOUR IN DATABASE ====\\n")
        print(f"Tour name: {tour_name}")
        print(f"Request string: {request_string}")
        print(f"Zip path: {zip_path}")
        print(f"Initial coordinates: lat={lat}, lng={lng}")
        
        # ALWAYS get coordinates from coordinates-fromai service
        print("\\n==== FORCING COORDINATES RETRIEVAL FROM COORDINATES-FROMAI ====\\n")
        print(f"Location: {request_string or tour_name}")
        
        # Direct call to coordinates-fromai service
        try:
            import requests
            import urllib.parse
            
            # URL-encode the location
            location = request_string or tour_name
            encoded_location = urllib.parse.quote(location)
            
            # Make the request to the coordinates-fromai service
            url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"
            print(f"Requesting coordinates from: {url}")
            
            response = requests.get(url, timeout=30)
            
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if "coordinates" in data and len(data["coordinates"]) >= 2:
                    coords = (data["coordinates"][0], data["coordinates"][1])
                    print(f"Received coordinates: lat={coords[0]}, lng={coords[1]}")
                    # Override any previous coordinates
                    lat, lng = coords
                else:
                    print(f"Invalid response format: {data}")
            else:
                print(f"Error response: {response.text}")
        except Exception as e:
            print(f"Error calling coordinates-fromai service: {e}")
        
        print(f"Final coordinates to store: lat={lat}, lng={lng}")
        
        # Read the ZIP file as binary data
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
        # Connect to the database
        conn = psycopg2.connect(
            host="postgres-2",
            port=5432,
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Check if the audio_tours table has the necessary columns
        try:
            # Check if audio_tour column exists
            cur.execute(\"\"\"
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'audio_tour'
            \"\"\")
            has_audio_tour = cur.fetchone() is not None
            
            # Check if lat/lng columns exist
            cur.execute(\"\"\"
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'lat'
            \"\"\")
            has_lat = cur.fetchone() is not None
            
            # Check if number_requested column exists
            cur.execute(\"\"\"
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'number_requested'
            \"\"\")
            has_number_requested = cur.fetchone() is not None
            
            # Add missing columns if needed
            if not has_audio_tour:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN audio_tour BYTEA")
                print("Added audio_tour column")
            
            if not has_lat:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN lat DOUBLE PRECISION")
                cur.execute("ALTER TABLE audio_tours ADD COLUMN lng DOUBLE PRECISION")
                print("Added lat/lng columns")
            
            if not has_number_requested:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN number_requested INTEGER NOT NULL DEFAULT 0")
                print("Added number_requested column")
            
            conn.commit()
        except Exception as e:
            print(f"Error checking table structure: {e}")
            conn.rollback()
        
        # Check if tour already exists
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name = %s AND request_string = %s",
            (tour_name, request_string)
        )
        existing_tour = cur.fetchone()
        
        if existing_tour:
            # Update existing tour
            if has_audio_tour and has_lat and has_number_requested:
                cur.execute(
                    \"\"\"
                    UPDATE audio_tours 
                    SET audio_tour = %s, number_requested = number_requested + 1, lat = %s, lng = %s
                    WHERE id = %s
                    \"\"\",
                    (psycopg2.Binary(zip_data), lat, lng, existing_tour[0])
                )
            else:
                # Fallback if columns don't exist
                cur.execute(
                    \"\"\"
                    UPDATE audio_tours 
                    SET tour_name = %s, request_string = %s
                    WHERE id = %s
                    \"\"\",
                    (tour_name, request_string, existing_tour[0])
                )
            print(f"Updated existing tour: {tour_name}")
        else:
            # Insert new tour
            if has_audio_tour and has_lat and has_number_requested:
                cur.execute(
                    \"\"\"
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    \"\"\",
                    (tour_name, request_string, psycopg2.Binary(zip_data), 1, lat, lng)
                )
            else:
                # Fallback if columns don't exist
                cur.execute(
                    \"\"\"
                    INSERT INTO audio_tours (tour_name, request_string)
                    VALUES (%s, %s)
                    \"\"\",
                    (tour_name, request_string)
                )
            print(f"Inserted new tour: {tour_name}")
        
        # Commit the transaction
        conn.commit()
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        print("\\n==== TOUR STORED WITH COORDINATES ====\\n")
        print(f"Tour: {tour_name}")
        print(f"Coordinates: lat={lat}, lng={lng}")
        
        return True
        
    except Exception as e:
        print(f"Error storing audio tour: {e}")
        return False
"""
        
        # Find the start and end of the store_audio_tour function
        start_index = service_py.find("def store_audio_tour(")
        end_index = service_py.find("def orchestrate_tour_async(", start_index)
        
        # Replace the function
        new_service_py = service_py[:start_index] + new_function + service_py[end_index:]
        
        # Write the updated file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_service_py)
        
        print("Updated store_audio_tour function in tour_orchestrator_service.py")
        
        return True
    except Exception as e:
        print(f"Error fixing store_audio_tour: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Directly Modifying store_audio_tour Function =====\n")
    
    success = fix_store_audio_tour()
    
    if success:
        print("\nstore_audio_tour function modified successfully!")
        print("\nNow restart the tour orchestrator service with:")
        print("docker-compose restart tour-orchestrator")
    else:
        print("\nFailed to modify store_audio_tour function")
        sys.exit(1)

if __name__ == "__main__":
    main()