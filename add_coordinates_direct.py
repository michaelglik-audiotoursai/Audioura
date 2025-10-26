#!/usr/bin/env python3
"""
Script to directly add the coordinates endpoint to the tour-generator service.
"""
import subprocess
import sys
import time

def add_coordinates_endpoint_direct():
    """Directly add the coordinates endpoint to the tour-generator service."""
    try:
        print("Creating coordinates endpoint code...")
        
        # Create the endpoint code
        endpoint_code = """
# Coordinates endpoint for getting coordinates from OpenAI
@app.route('/coordinates/<location>', methods=['GET'])
def get_coordinates(location):
    \"\"\"Get coordinates for a location using OpenAI API.\"\"\"
    try:
        # Log the request
        print(f"\\n==== COORDINATES REQUEST: {location} ====\\n")
        
        # Create a prompt that asks for coordinates
        prompt = f"What are the latitude and longitude coordinates for {location}? Please respond with only the decimal coordinates in the format 'latitude, longitude' without any other text."
        
        # Use the OpenAI API to get coordinates
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides precise geographic coordinates."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        # Extract the coordinates from the response
        coordinates_text = response.choices[0].message.content.strip()
        print(f"OpenAI response: {coordinates_text}")
        
        # Parse the coordinates
        import re
        
        # Try to extract decimal numbers
        numbers = re.findall(r'-?\\d+\\.\\d+', coordinates_text)
        if len(numbers) >= 2:
            lat = float(numbers[0])
            lng = float(numbers[1])
            print(f"Parsed coordinates: lat={lat}, lng={lng}")
            return jsonify({"coordinates": [lat, lng]})
        
        # Try comma-separated format
        parts = coordinates_text.split(",")
        if len(parts) >= 2:
            try:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                print(f"Parsed coordinates: lat={lat}, lng={lng}")
                return jsonify({"coordinates": [lat, lng]})
            except ValueError:
                pass
        
        # If we get here, parsing failed
        print(f"Failed to parse coordinates from: {coordinates_text}")
        return jsonify({"error": "Failed to parse coordinates"}), 400
    except Exception as e:
        print(f"Error getting coordinates: {e}")
        return jsonify({"error": str(e)}), 500
"""
        
        # Write the endpoint code to a file
        with open("coordinates_endpoint.py", "w") as f:
            f.write(endpoint_code)
        
        print("Created coordinates_endpoint.py")
        
        # Get the current app.py file from the container
        print("Getting current app.py from container...")
        result = subprocess.run(
            ["docker", "cp", "development-tour-generator-1:/app/app.py", "./app.py.backup"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error getting app.py: {result.stderr}")
            return False
        
        print("Got app.py.backup")
        
        # Read the current app.py file
        with open("app.py.backup", "r") as f:
            app_py = f.read()
        
        # Check if the endpoint already exists
        if "@app.route('/coordinates/" in app_py:
            print("Coordinates endpoint already exists in app.py")
            return True
        
        # Add the endpoint to the app.py file
        with open("app.py.new", "w") as f:
            f.write(app_py)
            f.write("\n\n# Added coordinates endpoint\n")
            f.write(endpoint_code)
        
        print("Created app.py.new with coordinates endpoint")
        
        # Copy the new app.py file to the container
        result = subprocess.run(
            ["docker", "cp", "./app.py.new", "development-tour-generator-1:/app/app.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying app.py to container: {result.stderr}")
            return False
        
        print("Copied app.py to container")
        
        # Restart the tour-generator service
        print("Restarting tour-generator service...")
        result = subprocess.run(
            ["docker", "restart", "development-tour-generator-1"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting service: {result.stderr}")
            return False
        
        print("Tour-generator service restarted")
        
        # Wait for the service to start
        print("Waiting for service to start...")
        time.sleep(10)
        
        # Test the endpoint
        print("Testing the coordinates endpoint...")
        test_command = "curl -s http://tour-generator:5000/coordinates/Keene%20Public%20Library%2C%20Keene%2C%20NH"
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "bash", "-c", test_command],
            capture_output=True,
            text=True
        )
        
        print("Test result:")
        print(result.stdout)
        
        if "coordinates" in result.stdout:
            print("Coordinates endpoint is working!")
            return True
        else:
            print("Coordinates endpoint is not working")
            return False
    except Exception as e:
        print(f"Error adding coordinates endpoint: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Directly Adding Coordinates Endpoint =====\n")
    
    success = add_coordinates_endpoint_direct()
    
    if success:
        print("\nCoordinates endpoint added successfully!")
    else:
        print("\nFailed to add coordinates endpoint")
        sys.exit(1)

if __name__ == "__main__":
    main()