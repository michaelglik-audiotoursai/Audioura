#!/usr/bin/env python3
"""
Script to verify the coordinates endpoint in the tour-generator service.
"""
import subprocess
import sys

def verify_coordinates_endpoint():
    """Verify that the coordinates endpoint exists in the tour-generator service."""
    try:
        print("Checking if the coordinates endpoint exists in the tour-generator service...")
        
        # Check if the endpoint is in the app.py file
        result = subprocess.run(
            ["docker", "exec", "development-tour-generator-1", "grep", "-A", "5", "'/coordinates/'", "/app/app.py"],
            capture_output=True,
            text=True
        )
        
        if "@app.route('/coordinates/" in result.stdout:
            print("Found coordinates endpoint in app.py:")
            print(result.stdout)
            return True
        else:
            print("Coordinates endpoint not found in app.py")
            
            # Check if we need to add it
            print("\nAdding coordinates endpoint to app.py...")
            
            # Create the endpoint code
            endpoint_code = """
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
            
            # Write the endpoint code to a temporary file
            with open("coordinates_endpoint.py", "w") as f:
                f.write(endpoint_code)
            
            # Copy the endpoint code to the tour-generator container
            result = subprocess.run(
                ["docker", "cp", "coordinates_endpoint.py", "development-tour-generator-1:/app/"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Error copying endpoint code to container: {result.stderr}")
                return False
            
            # Add the endpoint to app.py
            result = subprocess.run(
                ["docker", "exec", "development-tour-generator-1", "bash", "-c", "cat /app/coordinates_endpoint.py >> /app/app.py"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Error adding endpoint to app.py: {result.stderr}")
                return False
            
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
            import time
            print("Waiting for service to start...")
            time.sleep(5)
            
            # Verify the endpoint was added
            result = subprocess.run(
                ["docker", "exec", "development-tour-generator-1", "grep", "-A", "5", "'/coordinates/'", "/app/app.py"],
                capture_output=True,
                text=True
            )
            
            if "@app.route('/coordinates/" in result.stdout:
                print("Successfully added coordinates endpoint to app.py:")
                print(result.stdout)
                return True
            else:
                print("Failed to add coordinates endpoint to app.py")
                return False
    except Exception as e:
        print(f"Error verifying coordinates endpoint: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Verifying Coordinates Endpoint =====\n")
    
    success = verify_coordinates_endpoint()
    
    if success:
        print("\nCoordinates endpoint verification successful!")
    else:
        print("\nCoordinates endpoint verification failed")
        sys.exit(1)

if __name__ == "__main__":
    main()