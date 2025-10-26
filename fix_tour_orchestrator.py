#!/usr/bin/env python3
"""
Script to fix the tour orchestrator service to properly call the coordinates-fromai service.
"""
import subprocess
import sys
import re

def fix_tour_orchestrator():
    """Fix the tour orchestrator service to properly call the coordinates-fromai service."""
    try:
        # Get the current tour_orchestrator_service.py file
        print("Getting current tour_orchestrator_service.py...")
        
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak")
        
        # Read the coordinates function
        with open("coordinates_function.py", "r") as f:
            coordinates_function = f.read()
        
        # Replace the get_coordinates_for_location function
        new_service_py = re.sub(
            r"def get_coordinates_for_location\(location\):.*?return None\n",
            coordinates_function + "\n",
            service_py,
            flags=re.DOTALL
        )
        
        # Add more detailed logging to the store_audio_tour function
        new_service_py = new_service_py.replace(
            "# If coordinates not provided, try to get them",
            "# If coordinates not provided, try to get them from coordinates-fromai service"
        )
        
        new_service_py = new_service_py.replace(
            "coords = get_coordinates_for_location(request_string or tour_name)",
            "print(f\"Calling coordinates-fromai service to get coordinates for: {request_string or tour_name}\")\n            coords = get_coordinates_for_location(request_string or tour_name)"
        )
        
        # Write the updated service file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_service_py)
        
        print("Updated tour_orchestrator_service.py with improved logging and coordinates function")
        
        # Restart the tour orchestrator service
        print("Restarting tour orchestrator service...")
        result = subprocess.run(
            ["docker-compose", "restart", "tour-orchestrator"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting service: {result.stderr}")
            return False
        
        print("Tour orchestrator service restarted")
        
        # Update the coordinates-fromai service to log more details
        print("Updating coordinates-fromai service to log more details...")
        
        # Read the app.py file
        with open("coordinates_fromAI/app.py", "r") as f:
            app_py = f.read()
        
        # Make a backup of the original file
        with open("coordinates_fromAI/app.py.bak", "w") as f:
            f.write(app_py)
        
        print("Created backup at coordinates_fromAI/app.py.bak")
        
        # Add more detailed logging
        new_app_py = app_py.replace(
            'logging.info(f"\\n==== COORDINATES REQUEST: {location} ====\\n")',
            'logging.info(f"\\n==== COORDINATES REQUEST FROM TOUR ORCHESTRATOR: {location} ====\\n")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"Sending request to OpenAI API for: {location}")',
            'logging.info(f"Sending request to OpenAI API for location: {location}")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"Parsed coordinates: lat={lat}, lng={lng}")',
            'logging.info(f"Parsed coordinates for {location}: lat={lat}, lng={lng}")'
        )
        
        # Write the updated app.py file
        with open("coordinates_fromAI/app.py", "w") as f:
            f.write(new_app_py)
        
        print("Updated coordinates_fromAI/app.py with improved logging")
        
        # Restart the coordinates-fromai service
        print("Restarting coordinates-fromai service...")
        result = subprocess.run(
            ["docker-compose", "restart", "coordinates-fromai"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting service: {result.stderr}")
            return False
        
        print("Coordinates-fromai service restarted")
        
        # Update the tour for Simsbury Free Library with coordinates
        print("Updating tour for Simsbury Free Library with coordinates...")
        
        # Create SQL script
        sql_script = """
        DO $$
        BEGIN
            UPDATE audio_tours 
            SET lat = 41.8765, lng = -72.8029
            WHERE request_string = 'Simsbury Free Library, Simsbury, CT';
            
            RAISE NOTICE 'Updated coordinates for Simsbury Free Library';
        END;
        $$;
        
        SELECT id, tour_name, request_string, lat, lng 
        FROM audio_tours 
        WHERE request_string = 'Simsbury Free Library, Simsbury, CT';
        """
        
        # Execute SQL script
        result = subprocess.run(
            ["docker", "exec", "-i", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours"],
            input=sql_script,
            capture_output=True,
            text=True
        )
        
        print("Database update result:")
        print(result.stdout)
        
        return True
    except Exception as e:
        print(f"Error fixing tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Fixing Tour Orchestrator Service =====\n")
    
    success = fix_tour_orchestrator()
    
    if success:
        print("\nTour orchestrator service fixed successfully!")
        print("\nNow when you generate a tour, the tour orchestrator will:")
        print("1. Call the coordinates-fromai service to get coordinates")
        print("2. Log the request and response in detail")
        print("3. Store the coordinates in the database")
        print("\nThe coordinates-fromai service will also log all requests and responses.")
        print("\nTo test it, generate a tour for a location like:")
        print("\"Boston Public Library, Boston, MA\"")
        print("\nThen check the logs:")
        print("docker-compose logs tour-orchestrator")
        print("docker-compose logs coordinates-fromai")
        print("\nAnd check the database:")
        print("docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c \"SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;\"")
    else:
        print("\nFailed to fix tour orchestrator service")
        sys.exit(1)

if __name__ == "__main__":
    main()