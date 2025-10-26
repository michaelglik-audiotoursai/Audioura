#!/usr/bin/env python3
"""
Script to fix coordinates service issues according to requirements
"""
import re

def main():
    print("Fixing coordinates service issues...")
    
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # 1. Update the coordinates service port to 5004 (internal port)
    content = content.replace("http://coordinates-fromai:5006/coordinates/", "http://coordinates-fromai:5004/coordinates/")
    
    # 2. Update the get_coordinates_direct function
    old_function = """def get_coordinates_direct(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    print(f"\\n==== DIRECT COORDINATES REQUEST FOR: {location} ====")
    print(f"Time: {datetime.now().isoformat()}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service
        url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"
        print(f"Requesting URL: {url}")
        
        response = requests.get(url, timeout=60)
        
        print(f"Response status code: {response.status_code}")
        print(f"Response time: {datetime.now().isoformat()}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {data}")
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                print(f"Received coordinates: lat={lat}, lng={lng}")
                return (lat, lng)
            else:
                print(f"Invalid response format: {data}")
        else:
            print(f"Error response: {response.text}")
        
        print(f"No coordinates found for {location}")
        return None
    except Exception as e:
        print(f"Error getting coordinates from coordinates-fromai service: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return None"""
    
    new_function = """def get_coordinates_direct(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    print(f"\\n==== DIRECT COORDINATES REQUEST FOR: {location} ====")
    print(f"Time: {datetime.now().isoformat()}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service (internal port 5004)
        url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"
        print(f"Requesting URL: {url}")
        
        response = requests.get(url, timeout=60)
        
        print(f"Response status code: {response.status_code}")
        print(f"Response time: {datetime.now().isoformat()}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {data}")
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                print(f"Received coordinates: lat={lat}, lng={lng}")
                return (lat, lng)
            else:
                print(f"Invalid response format: {data}")
                print(f"ERROR: Invalid response format from coordinates service")
                return (0, 0)  # Return 0,0 as fallback
        else:
            print(f"Error response: {response.text}")
            print(f"ERROR: Failed to get coordinates from service: {response.status_code}")
            return (0, 0)  # Return 0,0 as fallback
    except Exception as e:
        print(f"ERROR: Exception while getting coordinates from coordinates-fromai service: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return (0, 0)  # Return 0,0 as fallback"""
    
    content = content.replace(old_function, new_function)
    
    # 3. Update the coordinates handling in orchestrate_tour_async
    pattern = r"if not coordinates or not isinstance\(coordinates, list\) or len\(coordinates\) < 2:.*?else:\s+print\(f\"WARNING: Could not get coordinates for \{location\}\"\)"
    replacement = """if not coordinates or not isinstance(coordinates, list) or len(coordinates) < 2:
            log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 1.5/8: Getting geo coordinates...")
            print(f"No coordinates received from tour generator, getting coordinates for: {location}")
            
            # Try to get coordinates using our function
            print(f"Calling get_coordinates_direct for: {location}")
            coords = get_coordinates_direct(location)
            print(f"Result from get_coordinates_direct: {coords}")
            if coords:
                lat, lng = coords
                coordinates = [lat, lng]
                print(f"Using coordinates: {coordinates}")
            else:
                print(f"ERROR: Could not get coordinates for {location}")
                # Use 0,0 as fallback
                coordinates = [0, 0]
                print(f"Using fallback coordinates: {coordinates}")"""
    
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # 4. Enhance logging for mobile app connections
    old_header = """@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    print(f"\\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")"""
    
    new_header = """@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    # Generate a complete tour from text to audio to web
    print(f"\\n==== INCOMING REQUEST FROM MOBILE APP: {datetime.now().isoformat()} ====")
    print(f"Remote address: {request.remote_addr}")"""
    
    content = content.replace(old_header, new_header)
    
    # Write the file
    with open("tour_orchestrator_service.py", "w") as f:
        f.write(content)
    
    print("Done! Fixed coordinates service issues according to requirements.")

if __name__ == "__main__":
    main()