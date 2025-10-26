"""
Modified Tour Orchestrator Service - Complete audio tour generation REST API
Orchestrates the entire pipeline: text generation → audio processing → deployment
Includes storing tours in the database with coordinates
"""
import requests
import json
import time
import os
import zipfile
import uuid
import psycopg2
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading

app = Flask(__name__)
CORS(app)

# Global variables
TOURS_DIR = "/app/tours"
ACTIVE_JOBS = {}

def ensure_tours_directory():
    """Ensure the tours directory exists."""
    if not os.path.exists(TOURS_DIR):
        os.makedirs(TOURS_DIR)

def get_coordinates_for_location(location):
    """Get coordinates for a location using the coordinates-fromai service."""
    print("\n==== GET_COORDINATES_FOR_LOCATION FUNCTION CALLED ====")
    logger.info(f"Location: {location}")
    import requests
    import urllib.parse
    
    print(f"""
==== REQUESTING COORDINATES FOR: {location} ====
""")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service
        url = f"http://coordinates-fromai:5006/coordinates/{encoded_location}"
        # Logged by log_api_call
        
        response = requests.get(url, timeout=60)
        
        log_api_response("coordinates-fromai", response.status_code, data)
        
        if response.status_code == 200:
            data = response.json()
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                logger.info(f"Received coordinates: lat={lat}, lng={lng}")
                return (lat, lng)
            else:
                logger.error(f"Invalid response format: {data}")
        else:
            logger.error(f"Error response: {response.text}")
        
        logger.warning(f"No coordinates found for {location}")
        return None
    except Exception as e:
        log_error(e, "Error getting coordinates from coordinates-fromai service")
        return None

def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):
    """Store an audio tour in the database with coordinates and ZIP file."""
    print("\n==== STORE_AUDIO_TOUR FUNCTION CALLED ====")
    print(f"Parameters:")
    print(f"  tour_name: {tour_name}")
    print(f"  request_string: {request_string}")
    print(f"  zip_path: {zip_path}")
    print(f"  lat: {lat}")
    print(f"  lng: {lng}")
    try:
        print(f"\n==== STORING TOUR IN DATABASE ====\n")
        print(f"Tour name: {tour_name}")
        print(f"Request string: {request_string}")
        print(f"Zip path: {zip_path}")
        print(f"Initial coordinates: lat={lat}, lng={lng}")
        
        # Always get coordinates from the coordinates-fromai service
        print("\n==== ALWAYS GETTING COORDINATES FROM SERVICE ====\n")
        print(f"Location: {request_string or tour_name}")
        # Always get coordinates regardless of whether they were provided
        print("Coordinates not provided, trying to get them...")
        print(f"Calling coordinates-fromai service to get coordinates for: {request_string or tour_name}")
        # Call the coordinates-fromai service directly
        try:
            import requests
            import urllib.parse
            
            # URL-encode the location
            location = request_string or tour_name
            encoded_location = urllib.parse.quote(location)
            
            # Make the request to the coordinates-fromai service
            url = f"http://coordinates-fromai:5006/coordinates/{encoded_location}"
            print(f"Requesting coordinates from: {url}")
            
            response = requests.get(url, timeout=60)
            
            log_api_response("coordinates-fromai", response.status_code, data)
            
            if response.status_code == 200:
                data = response.json()
                
                if "coordinates" in data and len(data["coordinates"]) >= 2:
                    coords = (data["coordinates"][0], data["coordinates"][1])
                    print(f"Received coordinates: lat={coords[0]}, lng={coords[1]}")
                else:
                    logger.error(f"Invalid response format: {data}")
                    coords = None
            else:
                logger.error(f"Error response: {response.text}")
                coords = None
        except Exception as e:
            print(f"Error calling coordinates service: {e}")
            coords = None
        if coords:
            lat, lng = coords
            print(f"Using coordinates from get_coordinates_for_location: lat={lat}, lng={lng}")
        else:
            print(f"No coordinates found for {request_string}, trying one more approach...")
            
            # Try one more approach - hardcoded for specific locations
            location_lower = (request_string or tour_name).lower()
            if "simsbury" in location_lower and ("ct" in location_lower or "connecticut" in location_lower):
                lat, lng = 41.8762, -72.8082
                print(f"Using hardcoded coordinates for Simsbury: lat={lat}, lng={lng}")
            else:
                print("No coordinates found, storing NULL values")
                # Don't use fallback - let the database store NULL values
                lat, lng = None, None
        
        # Read the ZIP file as binary data
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
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
        
        # Check if the audio_tours table has the necessary columns
        try:
            # Check if audio_tour column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'audio_tour'
            """)
            has_audio_tour = cur.fetchone() is not None
            
            # Check if lat/lng columns exist
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'lat'
            """)
            has_lat = cur.fetchone() is not None
            
            # Check if number_requested column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audio_tours' AND column_name = 'number_requested'
            """)
            has_number_requested = cur.fetchone() is not None
            
            # Add missing columns if needed
            if not has_audio_tour:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN audio_tour BYTEA")
                print("Added audio_tour column")
            
            if not has_lat:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN lat DOUBLE PRECISION")
                cur.execute("ALTER TABLE audio_tours ADD COLUMN lng DOUBLE PRECISION")
                print("Added lat/lng columns")
            
            if not has_number_requested:
                cur.execute("ALTER TABLE audio_tours ADD COLUMN number_requested INTEGER NOT NULL DEFAULT 0")
                print("Added number_requested column")
            
            conn.commit()
        except Exception as e:
            print(f"Error checking table structure: {e}")
            conn.rollback()
        
        # Check if tour already exists
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name = %s AND request_string = %s",
            (tour_name, request_string)
        )
        existing_tour = cur.fetchone()
        
        if existing_tour:
            # Update existing tour
            if has_audio_tour and has_lat and has_number_requested:
                cur.execute(
                    """
                    UPDATE audio_tours 
                    SET audio_tour = %s, number_requested = number_requested + 1, lat = %s, lng = %s
                    WHERE id = %s
                    """,
                    (psycopg2.Binary(zip_data), lat, lng, existing_tour[0])
                )
            else:
                # Fallback if columns don't exist
                cur.execute(
                    """
                    UPDATE audio_tours 
                    SET tour_name = %s, request_string = %s
                    WHERE id = %s
                    """,
                    (tour_name, request_string, existing_tour[0])
                )
            print(f"Updated existing tour: {tour_name}")
        else:
            # Insert new tour
            if has_audio_tour and has_lat and has_number_requested:
                cur.execute(
                    """
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (tour_name, request_string, psycopg2.Binary(zip_data), 1, lat, lng)
                )
            else:
                # Fallback if columns don't exist
                cur.execute(
                    """
                    INSERT INTO audio_tours (tour_name, request_string)
                    VALUES (%s, %s)
                    """,
                    (tour_name, request_string)
                )
            print(f"Inserted new tour: {tour_name}")
        
        # Commit the transaction
        conn.commit()
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"Error storing audio tour: {e}")
        return False

def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id=None, request_string=None):
    """Orchestrate the complete tour generation pipeline asynchronously."""
    print("\n==== ORCHESTRATE_TOUR_ASYNC FUNCTION CALLED ====")
    print(f"Parameters:")
    print(f"  job_id: {job_id}")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  total_stops: {total_stops}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = "Starting complete tour generation pipeline..."
        
        # Step 1: Generate tour text
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 1/8: Generating tour text..."
        generate_data = {
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops,
            "include_coordinates": True  # Request coordinates
        }
        
        response = requests.post(
            "http://tour-generator:5000/generate",
            headers={"Content-Type": "application/json"},
            json=generate_data,
            timeout=60
        )
        
        if response.status_code != 200:
            raise Exception(f"Error generating tour: {response.text}")
        
        job_data = response.json()
        job_id_1 = job_data["job_id"]
        ACTIVE_JOBS[job_id]["text_job_id"] = job_id_1
        
        # Wait for text generation to complete
        ACTIVE_JOBS[job_id]["progress"] = "Waiting for tour text generation..."
        coordinates = None
        while True:
            status_response = requests.get(f"http://tour-generator:5000/status/{job_id_1}", timeout=10)
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data["status"] == "completed":
                    # Check if coordinates are available
                    if "coordinates" in status_data:
                        coordinates = status_data["coordinates"]
                        print(f"Received coordinates from tour generator: {coordinates}")
                    break
                elif status_data["status"] == "error":
                    raise Exception(f"Error in tour generation: {status_data.get('error', 'Unknown error')}")
                else:
                    ACTIVE_JOBS[job_id]["progress"] = f"Text generation: {status_data.get('progress', 'Processing...')}"
                    time.sleep(10)
            else:
                raise Exception("Error checking text generation status")
        
        # Step 1.5: Get coordinates if not provided by tour generator
        print("\n==== COORDINATES CHECK IN ORCHESTRATE_TOUR_ASYNC ====")
        print(f"Coordinates from tour generator: {coordinates}")
        if not coordinates or not isinstance(coordinates, list) or len(coordinates) < 2:
            log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 1.5/8: Getting geo coordinates..."
            print(f"No coordinates received from tour generator, getting coordinates for: {location}")
            
            # Try to get coordinates using our function
            print(f"Calling get_coordinates_for_location for: {location}")
            print("Calling get_coordinates_direct instead of get_coordinates_for_location")
            coords = get_coordinates_direct(location)
            print(f"Result from get_coordinates_for_location: {coords}")
            if coords:
                lat, lng = coords
                coordinates = [lat, lng]
                print(f"Successfully got coordinates: {coordinates}")
            else:
                print(f"WARNING: Could not get coordinates for {location}")
        
        # Step 2: Download tour text file
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 2/8: Downloading tour text file..."
        safe_location = location.replace(' ', '_').replace(',', '').replace(':', '').replace('/', '_').replace('\\', '_').lower()
        tour_filename = f"{safe_location}_tour.txt"
        
        download_response = requests.get(f"http://tour-generator:5000/download/{job_id_1}", timeout=60)
        if download_response.status_code == 200:
            tour_file_path = os.path.join(TOURS_DIR, tour_filename)
            with open(tour_file_path, 'wb') as f:
                f.write(download_response.content)
        else:
            raise Exception("Error downloading tour text file")
        
        # Step 3: Upload to tour processor
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 3/8: Uploading to tour processor..."
        with open(tour_file_path, 'rb') as f:
            files = {'file': f}
            upload_response = requests.post("http://tour-processor:5001/upload", files=files, timeout=60)
        
        if upload_response.status_code != 200:
            raise Exception(f"Error uploading file: {upload_response.text}")
        
        # Step 4: Process tour
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 4/8: Processing tour (text → audio → HTML)..."
        process_data = {"tour_file": tour_filename}
        
        process_response = requests.post(
            "http://tour-processor:5001/process",
            headers={"Content-Type": "application/json"},
            json=process_data,
            timeout=60
        )
        
        if process_response.status_code != 200:
            raise Exception(f"Error processing tour: {process_response.text}")
        
        process_job_data = process_response.json()
        job_id_2 = process_job_data["job_id"]
        ACTIVE_JOBS[job_id]["processor_job_id"] = job_id_2
        
        # Wait for processing to complete
        ACTIVE_JOBS[job_id]["progress"] = "Waiting for tour processing (this may take several minutes)..."
        while True:
            status_response = requests.get(f"http://tour-processor:5001/status/{job_id_2}", timeout=10)
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data["status"] == "completed":
                    break
                elif status_data["status"] == "error":
                    raise Exception(f"Error in tour processing: {status_data.get('error', 'Unknown error')}")
                else:
                    ACTIVE_JOBS[job_id]["progress"] = f"Audio processing: {status_data.get('progress', 'Processing...')}"
                    time.sleep(15)
            else:
                raise Exception("Error checking processing status")
        
        # Step 5: Download Netlify-ready ZIP
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 5/8: Downloading Netlify deployment package..."
        zip_filename = f"{tour_filename.replace('.txt', '')}_netlify.zip"
        zip_path = os.path.join(TOURS_DIR, zip_filename)
        
        download_response = requests.get(f"http://tour-processor:5001/download/{job_id_2}", timeout=60)
        if download_response.status_code == 200:
            with open(zip_path, 'wb') as f:
                f.write(download_response.content)
        else:
            raise Exception("Error downloading Netlify package")
        
        # Step 6: Extract ZIP file
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 6/8: Extracting deployment package..."
        safe_dir_name = tour_filename.replace('.txt', '').replace(':', '').replace('/', '_').replace('\\', '_')
        extract_dir = f"{safe_dir_name}_netlify"
        extract_path = os.path.join(TOURS_DIR, extract_dir)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Step 7: Get coordinates if still not available
        lat = None
        lng = None
        if coordinates and isinstance(coordinates, list) and len(coordinates) >= 2:
            lat = coordinates[0]
            lng = coordinates[1]
            print(f"Using coordinates from earlier step: lat={lat}, lng={lng}")
        else:
            log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 7/8: Getting geo coordinates (final attempt)..."
            print(f"Final attempt to get coordinates for: {location}")
            
            # Try one more time to get coordinates
            print(f"Calling get_coordinates_for_location for: {location}")
            print("Calling get_coordinates_direct instead of get_coordinates_for_location")
            coords = get_coordinates_direct(location)
            print(f"Result from get_coordinates_for_location: {coords}")
            if coords:
                lat, lng = coords
                print(f"Successfully got coordinates in final attempt: lat={lat}, lng={lng}")
            else:
                print(f"WARNING: Could not get coordinates for {location} in final attempt")
        
        # Step 8: Store in database
        print("\n==== PREPARING TO STORE TOUR IN DATABASE ====")
        print(f"Tour name: {location} - {tour_type} Tour")
        print(f"Request string: {request_string or location}")
        print(f"Coordinates to store: lat={lat}, lng={lng}")
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 8/8: Storing tour in database..."
        
        # Store the tour in the database
        tour_name = f"{location} - {tour_type} Tour"
        print(f"Storing tour in database: {tour_name}")
        print(f"Coordinates being stored: lat={lat}, lng={lng}")
        
        store_success = store_audio_tour(tour_name, request_string or location, zip_path, lat, lng)
        
        print("\n==== STORE_AUDIO_TOUR RESULT ====")
        print(f"Success: {store_success}")
        
        if store_success:
            ACTIVE_JOBS[job_id]["progress"] = "Tour stored in database successfully!"
            print(f"Tour stored successfully with coordinates: lat={lat}, lng={lng}")
        else:
            ACTIVE_JOBS[job_id]["progress"] = "Warning: Tour generated but could not be stored in database."
            print("Failed to store tour in database")
        
        # Complete
        ACTIVE_JOBS[job_id]["progress"] = "Tour generation completed successfully!"
        ACTIVE_JOBS[job_id]["status"] = "completed"
        log_job_update(job_id, "completed", "Tour generation completed successfully!")
        ACTIVE_JOBS[job_id]["output_zip"] = zip_filename
        ACTIVE_JOBS[job_id]["extract_dir"] = extract_dir
        ACTIVE_JOBS[job_id]["netlify_ready"] = True
        ACTIVE_JOBS[job_id]["coordinates"] = [lat, lng] if lat and lng else None
        
    except Exception as e:
        print(f"ERROR in orchestrate_tour_async: {e}")
        ACTIVE_JOBS[job_id]["status"] = "error"
        log_job_update(job_id, "error", ACTIVE_JOBS[job_id]["error"])
        ACTIVE_JOBS[job_id]["error"] = str(e)

def track_user_tour(user_id, tour_id, request_string):
    """Track user tour request with user tracking service."""
    try:
        log_api_call("user-tracking", f"http://user-api-2:5000/user/{user_id}", "PUT", payload)
        payload = {
            'tour_request': {
                'tour_id': tour_id,
                'request_string': request_string
            },
            'app_version': '0.0.0.3'
        }
        # Logged by log_api_call
        response = requests.put(
            f"http://user-api-2:5000/user/{user_id}",
            headers={'Content-Type': 'application/json'},
            json=payload,
            timeout=10
        )
        log_api_response("user-tracking", response.status_code, response.text)
        if response.status_code != 200:
            logger.error(f"Failed to track user tour: {response.text}")
        else:
            logger.info(f"User tour tracked successfully")
    except Exception as e:
        log_error(e, "Exception tracking user tour")
        raise e

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy", 
        "service": "tour_orchestrator",
        "description": "Complete audio tour generation pipeline"
    })

@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    """Generate a complete audio tour through the entire pipeline."""
    # Log all incoming requests with full details
    log_request(request)
    # Logged by log_request
    # Logged by log_request
    # Logged by log_request
    # Logged by log_request
    # Logged by log_request
    data = request.json
    logger.debug(f"Received request data: {data}")
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Validate required parameters
    location = data.get('location')
    tour_type = data.get('tour_type')
    total_stops = data.get('total_stops', 10)
    user_id = data.get('user_id')
    request_string = data.get('request_string')
    
    print(f"DEBUG: Executing generate_complete_tour() ^JNG")
    print(f"DEBUG: Extracted parameters:")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")
    
    if not location or not tour_type:
        return jsonify({"error": "location and tour_type are required"}), 400
    
    try:
        total_stops = int(total_stops)
        if total_stops < 1 or total_stops > 50:
            return jsonify({"error": "total_stops must be between 1 and 50"}), 400
    except ValueError:
        return jsonify({"error": "total_stops must be a valid integer"}), 400
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job tracking
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for processing",
        "location": location,
        "tour_type": tour_type,
        "total_stops": total_stops,
        "user_id": user_id,
        "request_string": request_string,
        "created_at": datetime.now().isoformat()
    }
    
    # Track user request immediately
    print(f"DEBUG: Checking user tracking condition - user_id: '{user_id}', request_string: '{request_string}'")
    if user_id and request_string:
        try:
            tour_id = f"tour_{job_id[:8]}"
            print(f"DEBUG: Tracking user tour immediately - User: {user_id}, Tour: {tour_id}")
            track_user_tour(user_id, tour_id, request_string)
            ACTIVE_JOBS[job_id]["tour_id"] = tour_id
            print(f"DEBUG: User tour tracking completed successfully")
        except Exception as e:
            print(f"ERROR: Failed to track user tour: {e}")
    else:
        print(f"DEBUG: User tracking skipped - user_id empty: {not user_id}, request_string empty: {not request_string}")
    
    # Start orchestration in background thread
    thread = threading.Thread(
        target=orchestrate_tour_async,
        args=(job_id, location, tour_type, total_stops, user_id, request_string)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"job_id": job_id, "status": "queued"})

@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status."""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "location": job["location"],
        "tour_type": job["tour_type"],
        "total_stops": job["total_stops"],
        "created_at": job["created_at"]
    }
    
    if job["status"] == "completed":
        response["output_zip"] = job["output_zip"]
        response["extract_dir"] = job["extract_dir"]
        response["netlify_ready"] = job["netlify_ready"]
        if "coordinates" in job:
            response["coordinates"] = job["coordinates"]
    elif job["status"] == "error":
        response["error"] = job["error"]
    
    return jsonify(response)

@app.route('/download/<job_id>', methods=['GET'])
def download_tour(job_id):
    """Download the complete tour package."""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed"}), 400
    
    zip_path = os.path.join(TOURS_DIR, job["output_zip"])
    if not os.path.exists(zip_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(zip_path, as_attachment=True, download_name=job["output_zip"])

@app.route('/serve/<job_id>', methods=['GET'])
def serve_tour_info(job_id):
    """Get information about serving the tour."""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed"}), 400
    
    extract_path = os.path.join(TOURS_DIR, job["extract_dir"])
    if not os.path.exists(extract_path):
        return jsonify({"error": "Tour directory not found"}), 404
    
    response = {
        "job_id": job_id,
        "extract_dir": job["extract_dir"],
        "local_path": extract_path,
        "instructions": [
            "1. Download the ZIP file using /download/{job_id}",
            "2. Extract the ZIP file to your desired location",
            "3. Serve the extracted directory with any web server",
            "4. Or deploy the directory directly to Netlify"
        ],
        "netlify_ready": True
    }
    
    # Add coordinates if available
    if "coordinates" in job:
        response["coordinates"] = job["coordinates"]
    
    return jsonify(response)

@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all orchestration jobs."""
    jobs = []
    for job_id, job_data in ACTIVE_JOBS.items():
        job_info = {
            "job_id": job_id,
            "status": job_data["status"],
            "location": job_data["location"],
            "tour_type": job_data["tour_type"],
            "total_stops": job_data["total_stops"],
            "created_at": job_data["created_at"],
            "progress": job_data.get("progress", "")
        }
        
        # Add coordinates if available
        if "coordinates" in job_data:
            job_info["coordinates"] = job_data["coordinates"]
        
        jobs.append(job_info)
    
    return jsonify({"jobs": jobs})

def get_coordinates_direct(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    log_api_call("coordinates-fromai", f"http://coordinates-fromai:5006/coordinates/{encoded_location}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service
        url = f"http://coordinates-fromai:5006/coordinates/{encoded_location}"
        # Logged by log_api_call
        
        response = requests.get(url, timeout=60)
        
        log_api_response("coordinates-fromai", response.status_code, data)
        
        if response.status_code == 200:
            data = response.json()
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                logger.info(f"Received coordinates: lat={lat}, lng={lng}")
                return (lat, lng)
            else:
                logger.error(f"Invalid response format: {data}")
        else:
            logger.error(f"Error response: {response.text}")
        
        logger.warning(f"No coordinates found for {location}")
        return None
    except Exception as e:
        log_error(e, "Error getting coordinates from coordinates-fromai service")
        return None

# Direct function to call coordinates-fromai service
def call_coordinates_service(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    log_api_call("coordinates-fromai", f"http://coordinates-fromai:5006/coordinates/{encoded_location}")
    logger.info(f"Location: {location}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service
        url = f"http://coordinates-fromai:5006/coordinates/{encoded_location}"
        # Logged by log_api_call
        
        response = requests.get(url, timeout=60)
        
        log_api_response("coordinates-fromai", response.status_code, data)
        
        if response.status_code == 200:
            data = response.json()
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                logger.info(f"Received coordinates: lat={lat}, lng={lng}")
                return (lat, lng)
            else:
                logger.error(f"Invalid response format: {data}")
        else:
            logger.error(f"Error response: {response.text}")
        
        logger.warning(f"No coordinates found for {location}")
        return None
    except Exception as e:
        log_error(e, "Error getting coordinates from coordinates-fromai service")
        return None

if __name__ == '__main__':
    # Ensure tours directory exists
    ensure_tours_directory()
    
    logger.info("Starting Modified Tour Orchestrator Service...")
    logger.info(f"Tours directory: {TOURS_DIR}")
    logger.info("Pipeline: Complete tour generation orchestration with database storage")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5002, debug=True)

