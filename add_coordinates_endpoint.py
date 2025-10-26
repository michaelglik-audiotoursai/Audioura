#!/usr/bin/env python3
"""
Script to add a coordinates endpoint to the tour-generator service.
"""
import subprocess
import sys
import time

def add_coordinates_endpoint():
    """Add a coordinates endpoint to the tour-generator service."""
    try:
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
        
        print("Created coordinates_endpoint.py")
        
        # Copy the endpoint code to the tour-generator container
        result = subprocess.run(
            ["docker", "cp", "coordinates_endpoint.py", "development-tour-generator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying endpoint code to container: {result.stderr}")
            return False
        
        print("Copied endpoint code to container")
        
        # Create a script to add the endpoint to app.py
        apply_script = """#!/bin/bash
echo "Adding coordinates endpoint to app.py"
cat /app/coordinates_endpoint.py >> /app/app.py
echo "Endpoint added"
"""
        
        # Write the apply script to a temporary file
        with open("add_endpoint.sh", "w") as f:
            f.write(apply_script)
        
        print("Created add_endpoint.sh")
        
        # Copy the apply script to the tour-generator container
        result = subprocess.run(
            ["docker", "cp", "add_endpoint.sh", "development-tour-generator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying apply script to container: {result.stderr}")
            return False
        
        print("Copied apply script to container")
        
        # Make the apply script executable
        result = subprocess.run(
            ["docker", "exec", "development-tour-generator-1", "chmod", "+x", "/app/add_endpoint.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error making apply script executable: {result.stderr}")
            return False
        
        print("Made apply script executable")
        
        # Run the apply script
        result = subprocess.run(
            ["docker", "exec", "development-tour-generator-1", "/app/add_endpoint.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error applying endpoint: {result.stderr}")
            return False
        
        print("Applied endpoint:")
        print(result.stdout)
        
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
        time.sleep(5)
        
        # Test the endpoint
        print("Testing the coordinates endpoint...")
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "curl", "-s", "http://tour-generator:5000/coordinates/Keene%20Public%20Library,%20Keene,%20NH"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error testing endpoint: {result.stderr}")
            return False
        
        print("Endpoint test result:")
        print(result.stdout)
        
        return True
    except Exception as e:
        print(f"Error adding coordinates endpoint: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Adding Coordinates Endpoint to Tour Generator =====\n")
    
    success = add_coordinates_endpoint()
    
    if success:
        print("\nCoordinates endpoint added successfully!")
    else:
        print("\nFailed to add coordinates endpoint")
        sys.exit(1)

if __name__ == "__main__":
    main()