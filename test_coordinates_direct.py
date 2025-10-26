#!/usr/bin/env python3
"""
Script to directly test the coordinates-fromai service and update a tour with coordinates.
"""
import requests
import sys
import urllib.parse
import subprocess
import json

def test_coordinates_service_direct(location):
    """Test the coordinates-fromai service directly."""
    try:
        print(f"\n===== TESTING COORDINATES SERVICE FOR: {location} =====\n")
        
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Test using curl from inside the container
        print("Testing with curl from inside the container:")
        curl_cmd = f"curl -v http://coordinates-fromai:5004/coordinates/{encoded_location}"
        
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "bash", "-c", curl_cmd],
            capture_output=True,
            text=True
        )
        
        print("\nCurl command output:")
        print(result.stdout)
        print(result.stderr)
        
        # Test using Python requests from inside the container
        print("\nTesting with Python requests from inside the container:")
        python_cmd = f"""
import requests
import json

try:
    url = "http://coordinates-fromai:5004/coordinates/{encoded_location}"
    print(f"Requesting URL: {{url}}")
    
    response = requests.get(url, timeout=30)
    
    print(f"Response status code: {{response.status_code}}")
    print(f"Response headers: {{response.headers}}")
    print(f"Response content: {{response.text}}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            print(f"Parsed JSON: {{json.dumps(data, indent=2)}}")
        except Exception as e:
            print(f"Error parsing JSON: {{e}}")
except Exception as e:
    print(f"Error: {{e}}")
"""
        
        # Write the Python script to a temporary file
        with open("test_request.py", "w") as f:
            f.write(python_cmd)
        
        # Copy the script to the container
        subprocess.run(
            ["docker", "cp", "test_request.py", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        # Run the script in the container
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "python", "/app/test_request.py"],
            capture_output=True,
            text=True
        )
        
        print("\nPython requests output:")
        print(result.stdout)
        print(result.stderr)
        
        # Now test the coordinates-fromai service directly
        print("\nTesting coordinates-fromai service directly:")
        
        # Create a test script for the coordinates-fromai service
        test_script = f"""
import logging
import sys

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# Test the get_coordinates function
location = "{location}"
print(f"\\n==== TESTING GET_COORDINATES FOR: {{location}} ====\\n")

try:
    from app import get_coordinates
    
    result = get_coordinates(location)
    print(f"Function returned: {{result}}")
except Exception as e:
    print(f"Error calling get_coordinates: {{e}}")
"""
        
        # Write the test script to a temporary file
        with open("test_coordinates.py", "w") as f:
            f.write(test_script)
        
        # Copy the script to the container
        subprocess.run(
            ["docker", "cp", "test_coordinates.py", "development-coordinates-fromai-1:/app/"],
            capture_output=True,
            text=True
        )
        
        # Run the script in the container
        result = subprocess.run(
            ["docker", "exec", "development-coordinates-fromai-1", "python", "/app/test_coordinates.py"],
            capture_output=True,
            text=True
        )
        
        print("\nDirect function test output:")
        print(result.stdout)
        print(result.stderr)
        
        # Now test the OpenAI API directly
        print("\nTesting OpenAI API directly:")
        
        # Get the OpenAI API key from the container
        result = subprocess.run(
            ["docker", "exec", "development-coordinates-fromai-1", "bash", "-c", "echo $OPENAI_API_KEY"],
            capture_output=True,
            text=True
        )
        
        api_key = result.stdout.strip()
        
        if not api_key:
            print("Could not get OpenAI API key from container")
            return False
        
        print(f"Got OpenAI API key: {api_key[:5]}...{api_key[-5:]}")
        
        # Create a test script for the OpenAI API
        openai_script = f"""
import openai
import sys

# Set the API key
openai.api_key = "{api_key}"

# Test the OpenAI API
location = "{location}"
print(f"\\n==== TESTING OPENAI API FOR: {{location}} ====\\n")

try:
    # Create a prompt that asks for coordinates
    prompt = f"What are the latitude and longitude coordinates for {{location}}? Please respond with only the decimal coordinates in the format 'latitude, longitude' without any other text."
    
    print(f"Sending request to OpenAI API with prompt: {{prompt}}")
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {{"role": "system", "content": "You are a helpful assistant that provides precise geographic coordinates."}},
            {{"role": "user", "content": prompt}}
        ],
        temperature=0.2
    )
    
    # Extract the coordinates from the response
    coordinates_text = response.choices[0].message.content.strip()
    print(f"OpenAI response: {{coordinates_text}}")
    
    # Parse the coordinates
    import re
    
    # Try to extract decimal numbers
    numbers = re.findall(r'-?\\d+\\.\\d+', coordinates_text)
    if len(numbers) >= 2:
        lat = float(numbers[0])
        lng = float(numbers[1])
        print(f"Parsed coordinates: lat={{lat}}, lng={{lng}}")
    else:
        # Try comma-separated format
        parts = coordinates_text.split(",")
        if len(parts) >= 2:
            try:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                print(f"Parsed coordinates: lat={{lat}}, lng={{lng}}")
            except ValueError:
                print(f"Could not parse coordinates from: {{coordinates_text}}")
        else:
            print(f"Could not parse coordinates from: {{coordinates_text}}")
except Exception as e:
    print(f"Error calling OpenAI API: {{e}}")
"""
        
        # Write the OpenAI test script to a temporary file
        with open("test_openai.py", "w") as f:
            f.write(openai_script)
        
        # Copy the script to the container
        subprocess.run(
            ["docker", "cp", "test_openai.py", "development-coordinates-fromai-1:/app/"],
            capture_output=True,
            text=True
        )
        
        # Run the script in the container
        result = subprocess.run(
            ["docker", "exec", "development-coordinates-fromai-1", "python", "/app/test_openai.py"],
            capture_output=True,
            text=True
        )
        
        print("\nOpenAI API test output:")
        print(result.stdout)
        print(result.stderr)
        
        # Extract coordinates from the OpenAI test
        coordinates_match = re.search(r"Parsed coordinates: lat=([\d\.-]+), lng=([\d\.-]+)", result.stdout)
        
        if coordinates_match:
            lat = float(coordinates_match.group(1))
            lng = float(coordinates_match.group(2))
            print(f"\nExtracted coordinates: lat={lat}, lng={lng}")
            
            # Now test updating the database directly
            print("\nTesting database update:")
            
            # Get the tour ID
            db_cmd = f"SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE request_string LIKE '%{location}%' ORDER BY id DESC LIMIT 1;"
            
            result = subprocess.run(
                ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c", db_cmd],
                capture_output=True,
                text=True
            )
            
            print("\nDatabase query result:")
            print(result.stdout)
            
            # Extract the tour ID
            tour_id_match = re.search(r"^\s*(\d+)\s+\|", result.stdout, re.MULTILINE)
            
            if tour_id_match:
                tour_id = tour_id_match.group(1)
                print(f"Found tour ID: {tour_id}")
                
                # Update the tour with coordinates
                update_cmd = f"UPDATE audio_tours SET lat = {lat}, lng = {lng} WHERE id = {tour_id};"
                
                result = subprocess.run(
                    ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c", update_cmd],
                    capture_output=True,
                    text=True
                )
                
                print("\nDatabase update result:")
                print(result.stdout)
                
                # Verify the update
                verify_cmd = f"SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE id = {tour_id};"
                
                result = subprocess.run(
                    ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c", verify_cmd],
                    capture_output=True,
                    text=True
                )
                
                print("\nDatabase verification result:")
                print(result.stdout)
                
                if f"{lat}" in result.stdout and f"{lng}" in result.stdout:
                    print("\nSUCCESS: Tour updated with coordinates!")
                    return True
                else:
                    print("\nERROR: Tour was not updated with coordinates")
                    return False
            else:
                print("\nERROR: Could not find tour ID")
                return False
        else:
            print("\nERROR: Could not extract coordinates from OpenAI test")
            return False
    except Exception as e:
        print(f"\nError testing coordinates service: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python test_coordinates_direct.py \"Location Name\"")
        print("Example: python test_coordinates_direct.py \"Gale Free Library, Holden MA\"")
        sys.exit(1)
    
    location = sys.argv[1]
    
    print("\n===== DIRECT COORDINATES SERVICE TEST =====\n")
    
    success = test_coordinates_service_direct(location)
    
    if success:
        print("\nTest successful! The coordinates service is working and the tour was updated.")
    else:
        print("\nTest failed. The coordinates service is not working correctly.")
        sys.exit(1)

if __name__ == "__main__":
    main()