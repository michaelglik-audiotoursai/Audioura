#!/usr/bin/env python3
"""
Script to test the coordinates endpoint in the tour-generator service.
"""
import subprocess
import sys
import json
import urllib.parse

def test_coordinates_endpoint(location):
    """Test the coordinates endpoint in the tour-generator service using Docker exec."""
    try:
        print(f"Testing coordinates endpoint for: {location}")
        
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Use Docker exec to make the request from inside the container
        print(f"Using Docker exec to access the endpoint from inside the container")
        
        # Create the curl command
        curl_command = f"curl -s http://tour-generator:5000/coordinates/{encoded_location}"
        print(f"Command: {curl_command}")
        
        # Execute the command in the tour-orchestrator container
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "bash", "-c", curl_command],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error executing curl command: {result.stderr}")
            return False
        
        # Parse the response
        response_text = result.stdout.strip()
        print(f"Raw response: {response_text}")
        
        try:
            data = json.loads(response_text)
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                print(f"Received coordinates: lat={lat}, lng={lng}")
                
                # Test storing in database
                print("\n==== TESTING DATABASE STORAGE ====\n")
                print(f"Tour name: TEST - {location} Tour")
                print(f"Request string: TEST - {location}")
                print(f"Coordinates: lat={lat}, lng={lng}")
                
                # Use psql to insert into database
                psql_command = f"""
                DO $$
                DECLARE
                    tour_id integer;
                BEGIN
                    -- Check if test tour already exists
                    SELECT id INTO tour_id FROM audio_tours WHERE tour_name = 'TEST - {location} Tour';
                    
                    IF FOUND THEN
                        -- Update existing tour
                        UPDATE audio_tours SET lat = {lat}, lng = {lng} WHERE id = tour_id;
                        RAISE NOTICE 'Updated existing test tour with ID %', tour_id;
                    ELSE
                        -- Insert new tour
                        INSERT INTO audio_tours (tour_name, request_string, number_requested, lat, lng)
                        VALUES ('TEST - {location} Tour', 'TEST - {location}', 0, {lat}, {lng})
                        RETURNING id INTO tour_id;
                        RAISE NOTICE 'Created new test tour with ID %', tour_id;
                    END IF;
                END;
                $$;
                
                -- Verify the coordinates were stored correctly
                SELECT id, tour_name, lat, lng FROM audio_tours WHERE tour_name = 'TEST - {location} Tour';
                """
                
                # Execute the psql command
                db_result = subprocess.run(
                    ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c", psql_command],
                    capture_output=True,
                    text=True
                )
                
                print(db_result.stdout)
                
                if "ERROR" in db_result.stdout:
                    print(f"Database error: {db_result.stdout}")
                    return False
                
                return True
            else:
                print(f"Invalid response format: {data}")
        except json.JSONDecodeError:
            print(f"Invalid JSON response: {response_text}")
        
        return False
    except Exception as e:
        print(f"Error testing coordinates endpoint: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python test_coordinates_endpoint.py \"Location Name\"")
        print("Example: python test_coordinates_endpoint.py \"Keene Public Library, Keene, NH\"")
        sys.exit(1)
    
    location = sys.argv[1]
    
    print("\n===== Testing Coordinates Endpoint =====\n")
    
    success = test_coordinates_endpoint(location)
    
    if success:
        print("\nCoordinates endpoint test successful!")
    else:
        print("\nCoordinates endpoint test failed")
        sys.exit(1)

if __name__ == "__main__":
    main()