#!/usr/bin/env python3
"""
Script to add comprehensive logging to the tour orchestrator service.
"""
import subprocess
import sys
import re

def add_comprehensive_logging():
    """Add comprehensive logging to the tour orchestrator service."""
    try:
        # Get the current tour_orchestrator_service.py file
        print("Getting current tour_orchestrator_service.py...")
        
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak_logging", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak_logging")
        
        # Add logging to the generate_complete_tour function
        new_service_py = service_py.replace(
            "def generate_complete_tour():",
            """def generate_complete_tour():
    \"\"\"Generate a complete audio tour through the entire pipeline.\"\"\"
    # Log all incoming requests with full details
    print("\\n==== INCOMING REQUEST FROM MOBILE APP ====")
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data(as_text=True)}")
    print(f"Request JSON: {request.json if request.is_json else None}")
    print("==== END OF REQUEST DETAILS ====\\n")"""
        )
        
        # Add logging to the store_audio_tour function
        new_service_py = new_service_py.replace(
            "def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):",
            """def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):
    \"\"\"Store an audio tour in the database with coordinates and ZIP file.\"\"\"
    print("\\n==== STORE_AUDIO_TOUR FUNCTION CALLED ====")
    print(f"Parameters:")
    print(f"  tour_name: {tour_name}")
    print(f"  request_string: {request_string}")
    print(f"  zip_path: {zip_path}")
    print(f"  lat: {lat}")
    print(f"  lng: {lng}")"""
        )
        
        # Add logging to the get_coordinates_for_location function
        new_service_py = new_service_py.replace(
            "def get_coordinates_for_location(location):",
            """def get_coordinates_for_location(location):
    \"\"\"Get coordinates for a location using the coordinates-fromai service.\"\"\"
    print("\\n==== GET_COORDINATES_FOR_LOCATION FUNCTION CALLED ====")
    print(f"Location: {location}")"""
        )
        
        # Add logging to the orchestrate_tour_async function
        new_service_py = new_service_py.replace(
            "def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id=None, request_string=None):",
            """def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id=None, request_string=None):
    \"\"\"Orchestrate the complete tour generation pipeline asynchronously.\"\"\"
    print("\\n==== ORCHESTRATE_TOUR_ASYNC FUNCTION CALLED ====")
    print(f"Parameters:")
    print(f"  job_id: {job_id}")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  total_stops: {total_stops}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")"""
        )
        
        # Add logging before coordinates retrieval
        new_service_py = new_service_py.replace(
            "# Step 1.5: Get coordinates if not provided by tour generator",
            """# Step 1.5: Get coordinates if not provided by tour generator
        print("\\n==== COORDINATES CHECK IN ORCHESTRATE_TOUR_ASYNC ====")
        print(f"Coordinates from tour generator: {coordinates}")"""
        )
        
        # Add logging before calling get_coordinates_for_location
        new_service_py = new_service_py.replace(
            "coords = get_coordinates_for_location(location)",
            """print(f"Calling get_coordinates_for_location for: {location}")
            coords = get_coordinates_for_location(location)
            print(f"Result from get_coordinates_for_location: {coords}")"""
        )
        
        # Add logging before storing in database
        new_service_py = new_service_py.replace(
            "# Step 8: Store in database",
            """# Step 8: Store in database
        print("\\n==== PREPARING TO STORE TOUR IN DATABASE ====")
        print(f"Tour name: {location} - {tour_type} Tour")
        print(f"Request string: {request_string or location}")
        print(f"Coordinates to store: lat={lat}, lng={lng}")"""
        )
        
        # Add logging after storing in database
        new_service_py = new_service_py.replace(
            "if store_success:",
            """print("\\n==== STORE_AUDIO_TOUR RESULT ====")
        print(f"Success: {store_success}")
        
        if store_success:"""
        )
        
        # Write the updated service file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_service_py)
        
        print("Updated tour_orchestrator_service.py with comprehensive logging")
        
        # Update the coordinates-fromai service with improved logging
        print("Updating coordinates-fromai service with improved logging...")
        
        # Read the app.py file
        with open("coordinates_fromAI/app.py", "r") as f:
            app_py = f.read()
        
        # Make a backup of the original file
        with open("coordinates_fromAI/app.py.bak_logging", "w") as f:
            f.write(app_py)
        
        print("Created backup at coordinates_fromAI/app.py.bak_logging")
        
        # Add more detailed logging
        new_app_py = app_py.replace(
            '@app.route(\'/coordinates/<path:location>\', methods=[\'GET\'])',
            """@app.route('/coordinates/<path:location>', methods=['GET'])
@app.route('/coordinates/<path:location>/', methods=['GET'])"""
        )
        
        new_app_py = new_app_py.replace(
            'def get_coordinates(location):',
            """def get_coordinates(location):
    \"\"\"Get coordinates for a location using OpenAI API.\"\"\"
    print("\\n==== COORDINATES REQUEST RECEIVED ====")
    print(f"Location: {location}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request method: {request.method}")
    print(f"Request remote addr: {request.remote_addr}")"""
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"Sending request to OpenAI API for: {location}")',
            'print(f"Sending request to OpenAI API for: {location}")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"OpenAI response: {coordinates_text}")',
            'print(f"OpenAI response: {coordinates_text}")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"Parsed coordinates: lat={lat}, lng={lng}")',
            'print(f"Parsed coordinates for {location}: lat={lat}, lng={lng}")'
        )
        
        # Add logging for errors
        new_app_py = new_app_py.replace(
            'logging.error(f"Failed to parse coordinates from: {coordinates_text}")',
            'print(f"ERROR: Failed to parse coordinates from: {coordinates_text}")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.error(f"Error getting coordinates: {e}")',
            'print(f"ERROR: Error getting coordinates: {e}")'
        )
        
        # Write the updated app.py file
        with open("coordinates_fromAI/app.py", "w") as f:
            f.write(new_app_py)
        
        print("Updated coordinates_fromAI/app.py with improved logging")
        
        # Restart both services
        print("Restarting services...")
        
        result = subprocess.run(
            ["docker-compose", "restart", "coordinates-fromai", "tour-orchestrator"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting services: {result.stderr}")
            return False
        
        print("Services restarted with comprehensive logging")
        
        return True
    except Exception as e:
        print(f"Error adding comprehensive logging: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Adding Comprehensive Logging =====\n")
    
    success = add_comprehensive_logging()
    
    if success:
        print("\nComprehensive logging added successfully!")
        print("\nNow when you generate a tour from the mobile app, you will see:")
        print("1. Complete request details from the mobile app")
        print("2. All function calls with parameters and results")
        print("3. Detailed logging of the coordinates retrieval process")
        print("4. Database storage operations with parameters and results")
        print("\nTo check the logs:")
        print("docker-compose logs tour-orchestrator")
        print("docker-compose logs coordinates-fromai")
    else:
        print("\nFailed to add comprehensive logging")
        sys.exit(1)

if __name__ == "__main__":
    main()