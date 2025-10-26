#!/usr/bin/env python3
"""
Script to directly add coordinates to a tour in the database.
"""
import sys
import subprocess

def add_coordinates_to_tour(tour_name, location):
    """Add coordinates to a tour in the database."""
    try:
        print(f"Adding coordinates to tour: {tour_name}")
        print(f"Location: {location}")
        
        # Call the coordinates-fromai service directly
        print("Calling coordinates-fromai service...")
        
        # Create a Python script to run inside the container
        script = f"""
import requests
import urllib.parse
import psycopg2

# Function to get coordinates
def get_coordinates(location):
    print(f"Getting coordinates for: {location}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service
        url = f"http://coordinates-fromai:5004/coordinates/{{encoded_location}}"
        print(f"Requesting URL: {{url}}")
        
        response = requests.get(url, timeout=30)
        
        print(f"Response status code: {{response.status_code}}")
        
        if response.status_code == 200:
            data = response.json()
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                print(f"Received coordinates: lat={{lat}}, lng={{lng}}")
                return (lat, lng)
            else:
                print(f"Invalid response format: {{data}}")
        else:
            print(f"Error response: {{response.text}}")
        
        return None
    except Exception as e:
        print(f"Error getting coordinates: {{e}}")
        return None

# Get coordinates
coords = get_coordinates("{location}")

if coords:
    lat, lng = coords
    
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
    
    # Update the tour
    cur.execute(
        \"\"\"
        UPDATE audio_tours 
        SET lat = %s, lng = %s
        WHERE tour_name = %s
        \"\"\",
        (lat, lng, "{tour_name}")
    )
    
    # Commit the transaction
    conn.commit()
    
    # Close cursor and connection
    cur.close()
    conn.close()
    
    print(f"Updated tour {{'{tour_name}'}} with coordinates: lat={{lat}}, lng={{lng}}")
else:
    print(f"Could not get coordinates for {{'{location}'}}")
"""
        
        # Write the script to a file
        with open("add_coordinates_script.py", "w") as f:
            f.write(script)
        
        print("Created add_coordinates_script.py")
        
        # Copy the script to the container
        result = subprocess.run(
            ["docker", "cp", "add_coordinates_script.py", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying script: {result.stderr}")
            return False
        
        print("Copied script to container")
        
        # Run the script in the container
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "python", "/app/add_coordinates_script.py"],
            capture_output=True,
            text=True
        )
        
        print("Script output:")
        print(result.stdout)
        
        if result.returncode != 0:
            print(f"Error running script: {result.stderr}")
            return False
        
        # Verify the update
        result = subprocess.run(
            ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c",
             f"SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE tour_name = '{tour_name}';"],
            capture_output=True,
            text=True
        )
        
        print("Database verification:")
        print(result.stdout)
        
        return True
    except Exception as e:
        print(f"Error adding coordinates to tour: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 3:
        print("Usage: python add_coordinates_to_tour.py \"Tour Name\" \"Location\"")
        print("Example: python add_coordinates_to_tour.py \"tolland public library, tolland Connecticut - museum Tour\" \"tolland public library, tolland Connecticut\"")
        sys.exit(1)
    
    tour_name = sys.argv[1]
    location = sys.argv[2]
    
    print("\n===== Adding Coordinates to Tour =====\n")
    
    success = add_coordinates_to_tour(tour_name, location)
    
    if success:
        print("\nCoordinates added to tour successfully!")
    else:
        print("\nFailed to add coordinates to tour")
        sys.exit(1)

if __name__ == "__main__":
    main()