#!/usr/bin/env python3
"""
Script to verify that the tour orchestrator is calling the coordinates-fromai service.
"""
import requests
import sys
import time
import subprocess

def test_tour_generation(location):
    """Test generating a tour and check if coordinates are added."""
    try:
        print(f"Testing tour generation for: {location}")
        
        # First check if the services are running
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
        
        services = result.stdout.strip().split("\n")
        
        if "development-tour-orchestrator-1" not in services:
            print("ERROR: Tour orchestrator service is not running!")
            return False
        
        if "development-coordinates-fromai-1" not in services:
            print("ERROR: Coordinates-fromai service is not running!")
            return False
        
        print("Both services are running.")
        
        # Generate a tour
        print(f"\nGenerating a tour for: {location}")
        
        # Prepare the request data
        data = {
            "location": location,
            "tour_type": "museum",
            "total_stops": 4
        }
        
        # Send the request to the tour orchestrator
        response = requests.post(
            "http://localhost:5002/generate-complete-tour",
            json=data,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"Error generating tour: {response.text}")
            return False
        
        # Get the job ID
        job_data = response.json()
        job_id = job_data["job_id"]
        
        print(f"Tour generation started with job ID: {job_id}")
        
        # Wait for the tour to be generated
        print("Waiting for tour generation to complete...")
        
        max_wait_time = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            status_response = requests.get(f"http://localhost:5002/status/{job_id}", timeout=10)
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                
                if status_data["status"] == "completed":
                    print("Tour generation completed!")
                    break
                elif status_data["status"] == "error":
                    print(f"Error in tour generation: {status_data.get('error', 'Unknown error')}")
                    return False
                else:
                    print(f"Tour generation in progress: {status_data.get('progress', 'Processing...')}")
                    time.sleep(10)
            else:
                print(f"Error checking status: {status_response.text}")
                return False
        else:
            print("Tour generation timed out!")
            return False
        
        # Check the logs
        print("\nChecking tour orchestrator logs...")
        
        result = subprocess.run(
            ["docker", "logs", "development-tour-orchestrator-1", "--tail", "100"],
            capture_output=True,
            text=True
        )
        
        orchestrator_logs = result.stdout
        
        if f"REQUESTING COORDINATES FOR: {location}" in orchestrator_logs:
            print("Found coordinates request in tour orchestrator logs!")
        else:
            print("WARNING: Could not find coordinates request in tour orchestrator logs.")
        
        print("\nChecking coordinates-fromai logs...")
        
        result = subprocess.run(
            ["docker", "logs", "development-coordinates-fromai-1", "--tail", "100"],
            capture_output=True,
            text=True
        )
        
        coordinates_logs = result.stdout
        
        if f"COORDINATES REQUEST FROM TOUR ORCHESTRATOR: {location}" in coordinates_logs:
            print("Found coordinates request in coordinates-fromai logs!")
        else:
            print("WARNING: Could not find coordinates request in coordinates-fromai logs.")
        
        # Check the database
        print("\nChecking database for coordinates...")
        
        result = subprocess.run(
            ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c", 
             f"SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE tour_name LIKE '%{location}%' ORDER BY id DESC LIMIT 1;"],
            capture_output=True,
            text=True
        )
        
        print("Database query result:")
        print(result.stdout)
        
        if "lat |" in result.stdout and "lng" in result.stdout and "|" in result.stdout:
            print("Tour was stored in the database!")
            
            # Check if coordinates are present
            if "| |" in result.stdout:
                print("WARNING: Coordinates are NULL in the database.")
                return False
            else:
                print("SUCCESS: Coordinates are present in the database!")
                return True
        else:
            print("ERROR: Could not find the tour in the database.")
            return False
    except Exception as e:
        print(f"Error testing tour generation: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python test_tour_generation.py \"Location Name\"")
        print("Example: python test_tour_generation.py \"Boston Public Library, Boston, MA\"")
        sys.exit(1)
    
    location = sys.argv[1]
    
    print("\n===== Testing Tour Generation with Coordinates =====\n")
    
    success = test_tour_generation(location)
    
    if success:
        print("\nTest successful! The tour was generated with coordinates.")
    else:
        print("\nTest failed. The tour was not generated with coordinates.")
        sys.exit(1)

if __name__ == "__main__":
    main()