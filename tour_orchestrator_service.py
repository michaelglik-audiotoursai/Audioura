import os
import sys
import json
import uuid
import zipfile
import shutil
import time
import threading
import requests
import traceback
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_file, make_response

# ARCHITECTURAL NOTE: Directory Cleanup Policy
# - ZIP files are the PRIMARY storage format in database
# - Directories are TEMPORARY for processing/extraction only
# - After successful ZIP storage in database, directories are cleaned up
# - This prevents storage bloat and maintains clean architecture
# - Tour resolution service handles ZIP files, not directories

# Inter-service URLs (env-var-driven for Cloud Run, defaults for local Docker)
TOUR_GENERATOR_URL = os.getenv('TOUR_GENERATOR_URL', 'http://development-tour-generator-1:5000')
MODERNIZED_URL = os.getenv('MODERNIZED_URL', 'http://tour-generation-modernized-1:5021')
TRANSLATION_URL = os.getenv('TRANSLATION_URL', 'http://translation-service-1:5030')
TOUR_UPDATE_URL = os.getenv('TOUR_UPDATE_URL', 'http://development-tour-update-1:5001')
USER_API_URL = os.getenv('USER_API_URL', 'http://user-api-2:5000')
COORDINATES_URL = os.getenv('COORDINATES_URL', 'http://coordinates-fromai:5004')

# Configure unbuffered logging
import sys
sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__)

# CORS headers for web platform support
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.after_request
def after_request(response):
    return add_cors_headers(response)

# Handle preflight OPTIONS requests
@app.route('/health', methods=['OPTIONS'])
@app.route('/generate-complete-tour', methods=['OPTIONS'])
@app.route('/status/<job_id>', methods=['OPTIONS'])
@app.route('/download/<job_id>', methods=['OPTIONS'])
@app.route('/serve/<job_id>', methods=['OPTIONS'])
@app.route('/jobs', methods=['OPTIONS'])
def handle_options(*args, **kwargs):
    response = make_response()
    return add_cors_headers(response)

def sanitize_input(input_text):
    """Sanitize user input for security and filesystem safety"""
    if not input_text or not isinstance(input_text, str):
        return ""
    
    # Remove control characters and null bytes
    sanitized = re.sub(r'[\x00-\x1F\x7F]', '', input_text)
    
    # Replace filesystem-dangerous characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', sanitized)
    
    # Remove script injection characters
    sanitized = re.sub(r'[<>"\']', '', sanitized)
    
    # Normalize whitespace
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    # Limit length to prevent issues
    if len(sanitized) > 200:
        sanitized = sanitized[:200].strip()
    
    return sanitized
# Log all incoming requests
@app.before_request
def log_request_info():
    print(f"\n==== REQUEST RECEIVED: {datetime.now().isoformat()} ====")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote address: {request.remote_addr}")
    print(f"User agent: {request.headers.get('User-Agent', 'Unknown')}")


# Global variables
TOURS_DIR = "/app/tours"  # Docker volume mount point
ACTIVE_JOBS = {}  # Track running jobs

def ensure_tours_directory():
    """Ensure the tours directory exists."""
    if not os.path.exists(TOURS_DIR):
        os.makedirs(TOURS_DIR)
        print(f"Created tours directory: {TOURS_DIR}")
    else:
        print(f"Tours directory exists: {TOURS_DIR}")

def log_job_update(job_id, status, progress):
    """Update and log the status of a job."""
    if job_id in ACTIVE_JOBS:
        ACTIVE_JOBS[job_id]["status"] = status
        ACTIVE_JOBS[job_id]["progress"] = progress
        print(f"JOB UPDATE [{job_id}]: Status={status}, Progress={progress}")
    else:
        print(f"WARNING: Attempted to update non-existent job: {job_id}")

def store_audio_tour(tour_name, request_string, zip_path, lat, lng, tour_content=None):
    """Store the audio tour in the database with original tour content."""
    print(f"\n==== STORING AUDIO TOUR IN DATABASE: {datetime.now().isoformat()} ====")
    print(f"Tour name: {tour_name}")
    print(f"Request string: {request_string}")
    print(f"ZIP path: {zip_path}")
    print(f"Coordinates: lat={lat}, lng={lng}")
    print(f"Tour content length: {len(tour_content) if tour_content else 0} characters")
    
    try:
        import psycopg2
        # Connect to the database
        print(f"Connecting to database...")
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        print(f"Connected to database")
        
        # Check if audio_tours table exists
        print(f"Checking if audio_tours table exists...")
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'audio_tours'
            )
        """)
        table_exists = cur.fetchone()[0]
        print(f"Table exists: {table_exists}")
        
        if not table_exists:
            # Create table if it doesn't exist
            print(f"Creating audio_tours table...")
            cur.execute("""
                CREATE TABLE audio_tours (
                    id SERIAL PRIMARY KEY,
                    tour_name VARCHAR(255) NOT NULL,
                    request_string TEXT NOT NULL,
                    audio_tour BYTEA,
                    number_requested INTEGER NOT NULL DEFAULT 0,
                    lat DOUBLE PRECISION,
                    lng DOUBLE PRECISION
                )
            """)
            print("Created audio_tours table")
            conn.commit()
            has_audio_tour = True
            has_lat = True
            has_number_requested = True
        else:
            try:
                # Check if audio_tour column exists
                print(f"Checking if audio_tour column exists...")
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'audio_tours' AND column_name = 'audio_tour'
                """)
                has_audio_tour = cur.fetchone() is not None
                print(f"audio_tour column exists: {has_audio_tour}")
                
                # Check if lat/lng columns exist
                print(f"Checking if lat column exists...")
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'audio_tours' AND column_name = 'lat'
                """)
                has_lat = cur.fetchone() is not None
                print(f"lat column exists: {has_lat}")
                
                # Check if number_requested column exists
                print(f"Checking if number_requested column exists...")
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'audio_tours' AND column_name = 'number_requested'
                """)
                has_number_requested = cur.fetchone() is not None
                print(f"number_requested column exists: {has_number_requested}")
                
                # Add missing columns if needed
                if not has_audio_tour:
                    print(f"Adding audio_tour column...")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN audio_tour BYTEA")
                    print("Added audio_tour column")
                
                if not has_lat:
                    print(f"Adding lat/lng columns...")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN lat DOUBLE PRECISION")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN lng DOUBLE PRECISION")
                    print("Added lat/lng columns")
                
                if not has_number_requested:
                    print(f"Adding number_requested column...")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN number_requested INTEGER NOT NULL DEFAULT 0")
                    print("Added number_requested column")
                
                conn.commit()
                print(f"Table structure updated")
            except Exception as e:
                print(f"Error checking table structure: {e}")
                print(f"Traceback: {traceback.format_exc()}")
                conn.rollback()
        
        # Check if tour_content column exists
        print(f"Checking if tour_content column exists...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'audio_tours' AND column_name = 'tour_content'
        """)
        has_tour_content = cur.fetchone() is not None
        print(f"tour_content column exists: {has_tour_content}")
        
        # Check if tour already exists
        print(f"Checking if tour already exists...")
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name = %s AND request_string = %s",
            (tour_name, request_string)
        )
        existing_tour = cur.fetchone()
        print(f"Existing tour: {existing_tour}")
        
        # Read the ZIP file as binary data
        print(f"Reading ZIP file: {zip_path}")
        print(f"File exists: {os.path.exists(zip_path)}")
        print(f"File size: {os.path.getsize(zip_path) if os.path.exists(zip_path) else 'N/A'}")
        with open(zip_path, "rb") as f:
            zip_data = f.read()
        print(f"Read {len(zip_data)} bytes from ZIP file")
            
        if existing_tour:
            # Update existing tour
            print(f"Updating existing tour...")
            if has_audio_tour and has_lat and has_number_requested and has_tour_content:
                cur.execute(
                    """
                    UPDATE audio_tours 
                    SET audio_tour = %s, number_requested = number_requested + 1, lat = %s, lng = %s, tour_content = %s
                    WHERE id = %s
                    """,
                    (psycopg2.Binary(zip_data), lat, lng, tour_content, existing_tour[0])
                )
            elif has_audio_tour and has_lat and has_number_requested:
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
            print(f"Inserting new tour...")
            if has_audio_tour and has_lat and has_number_requested and has_tour_content:
                cur.execute(
                    """
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tour_name, request_string, psycopg2.Binary(zip_data), 1, lat, lng, tour_content, 'en')
                )
            elif has_audio_tour and has_lat and has_number_requested:
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
        print(f"Committing transaction...")
        conn.commit()
        print(f"Transaction committed")
        
        # Close cursor and connection
        print(f"Closing database connection...")
        cur.close()
        conn.close()
        print(f"Database connection closed")
        
        print(f"==== AUDIO TOUR STORED SUCCESSFULLY ====")
        return True
        
    except Exception as e:
        print(f"ERROR storing audio tour: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id=None, request_string=None, language='en'):
    """Orchestrate the complete tour generation pipeline asynchronously."""
    print(f"\n==== ORCHESTRATE_TOUR_ASYNC STARTED: {datetime.now().isoformat()} ====")
    print(f"Parameters:")
    print(f"  job_id: {job_id}")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  total_stops: {total_stops}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")
    print(f"  language: {language}")
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = "Starting complete tour generation pipeline..."
        
        # Step 1: Generate tour text first, then process with modernized service
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 1/5: Generating tour text...")
        generate_data = {
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops
        }
        
        print(f"Calling tour text generator API: {datetime.now().isoformat()}")
        print(f"Request data: {generate_data}")
        response = requests.post(
            f"{TOUR_GENERATOR_URL}/generate",
            headers={"Content-Type": "application/json"},
            json=generate_data,
            timeout=60
        )
        
        print(f"Tour generator API response: {response.status_code}")
        print(f"Response content: {response.text[:1000]}")
        if response.status_code != 200:
            raise Exception(f"Error generating tour: {response.text}")
        
        job_data = response.json()
        job_id_1 = job_data["job_id"]
        ACTIVE_JOBS[job_id]["text_job_id"] = job_id_1
        print(f"Tour text generator job ID: {job_id_1}")
        
        # Wait for text generation to complete
        ACTIVE_JOBS[job_id]["progress"] = "Waiting for tour text generation..."
        coordinates = None
        poll_count = 0
        tour_file = None
        while True:
            poll_count += 1
            print(f"Checking tour text generator status: {datetime.now().isoformat()} (Poll #{poll_count})")
            status_response = requests.get(f"{TOUR_GENERATOR_URL}/status/{job_id_1}", timeout=10)
            print(f"Status response: {status_response.status_code}")
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"Status data: {status_data}")
                
                if status_data["status"] == "completed":
                    tour_file = status_data.get("output_file")
                    if "coordinates" in status_data:
                        coordinates = status_data["coordinates"]
                        print(f"Received coordinates from tour generator: {coordinates}")
                    print(f"Tour text generation completed: {datetime.now().isoformat()}")
                    break
                elif status_data["status"] == "error":
                    error_msg = f"Error in tour text generation: {status_data.get('error', 'Unknown error')}"
                    print(f"ERROR: {error_msg}")
                    raise Exception(error_msg)
                else:
                    progress = status_data.get('progress', 'Processing...')
                    print(f"Tour text generation in progress: {progress}")
                    ACTIVE_JOBS[job_id]["progress"] = f"Text generation: {progress}"
                    time.sleep(10)
            else:
                error_msg = f"Error checking text generation status: {status_response.text}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
        
        # Step 1.5: Process with modernized service
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 1.5/5: Processing with modernized service...")
        if not tour_file:
            raise Exception("No tour file received from text generator")
        
        # Prefer tour_content (HTTP-based, Cloud Run compatible) over tour_file (volume-based)
        tour_content = status_data.get("tour_content")
        if tour_content:
            modernized_data = {"tour_content": tour_content}
            print(f"Using tour_content for modernized service ({len(tour_content)} chars)")
        else:
            modernized_data = {"tour_file": tour_file}
            print(f"Using tour_file for modernized service: {tour_file}")
        
        print(f"Calling MODERNIZED service: {datetime.now().isoformat()}")
        modernized_response = requests.post(
            f"{MODERNIZED_URL}/process",
            headers={"Content-Type": "application/json"},
            json=modernized_data,
            timeout=60
        )
        
        if modernized_response.status_code != 200:
            raise Exception(f"Error calling modernized service: {modernized_response.text}")
        
        modernized_job_data = modernized_response.json()
        modernized_job_id = modernized_job_data["job_id"]
        print(f"Modernized service job ID: {modernized_job_id}")
        
        # Wait for modernized processing to complete
        ACTIVE_JOBS[job_id]["progress"] = "Waiting for modernized processing..."
        while True:
            modernized_status_response = requests.get(f"{MODERNIZED_URL}/status/{modernized_job_id}", timeout=10)
            
            if modernized_status_response.status_code == 200:
                modernized_status_data = modernized_status_response.json()
                
                if modernized_status_data["status"] == "completed":
                    print(f"Modernized processing completed: {datetime.now().isoformat()}")
                    break
                elif modernized_status_data["status"] == "error":
                    error_msg = f"Error in modernized processing: {modernized_status_data.get('error', 'Unknown error')}"
                    print(f"ERROR: {error_msg}")
                    raise Exception(error_msg)
                else:
                    progress = modernized_status_data.get('progress', 'Processing...')
                    print(f"Modernized processing in progress: {progress}")
                    ACTIVE_JOBS[job_id]["progress"] = f"Modernized processing: {progress}"
                    time.sleep(5)
            else:
                error_msg = f"Error checking modernized processing status: {modernized_status_response.text}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
        
        # Step 1.5: Get coordinates if not provided by modernized service
        print("\n==== COORDINATES CHECK IN ORCHESTRATE_TOUR_ASYNC ====")
        print(f"Coordinates from modernized service: {coordinates}")
        if not coordinates or not isinstance(coordinates, list) or len(coordinates) < 2:
            print(f"No coordinates received from modernized service, getting coordinates for: {location}")
            
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
                print(f"Using fallback coordinates: {coordinates}")
        
        # Step 2: Download complete modernized tour ZIP
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 2/5: Downloading complete modernized tour...")
        safe_location = location.replace(' ', '_').replace(',', '').replace(':', '').replace('/', '_').replace('\\', '_').lower()
        
        print(f"Downloading complete tour from MODERNIZED service: {datetime.now().isoformat()}")
        download_response = requests.get(f"{MODERNIZED_URL}/download/{modernized_job_id}", timeout=60)
        print(f"Download response: {download_response.status_code}")
        
        if download_response.status_code == 200:
            print(f"Received complete modernized tour: {len(download_response.content)} bytes")
        else:
            error_msg = f"Error downloading modernized tour: {download_response.text}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        
        # Step 3: Save modernized tour ZIP with separate MP3/TXT files
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 3/5: Processing modernized tour ZIP...")
        print(f"MODERNIZED service returned complete tour with separate MP3/TXT files")
        
        zip_filename = f"{safe_location}_{tour_type}_{job_id[:8]}.zip"
        zip_path = os.path.join(TOURS_DIR, zip_filename)
        print(f"Saving modernized tour to: {zip_path}")
        with open(zip_path, 'wb') as f:
            f.write(download_response.content)
        ACTIVE_JOBS[job_id]["output_zip"] = zip_filename
        print(f"Modernized tour saved: {len(download_response.content)} bytes")
        print(f"File exists: {os.path.exists(zip_path)}")
        
        # Step 4: Extract modernized tour ZIP
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 4/5: Extracting modernized tour package...")
        extract_dir = f"{safe_location}_{tour_type}_{job_id[:8]}"
        extract_path = os.path.join(TOURS_DIR, extract_dir)
        print(f"Extracting ZIP file to: {extract_path}")
        os.makedirs(extract_path, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            print(f"ZIP file extracted successfully")
            print(f"Extracted files: {os.listdir(extract_path)}")
        except Exception as e:
            error_msg = f"Error extracting ZIP file: {e}"
            print(f"ERROR: {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")
            raise Exception(error_msg)
        
        ACTIVE_JOBS[job_id]["extract_dir"] = extract_dir
        
        # COUNT ASSERTION: ZIP must have exactly total_stops audio files
        expected_stops = ACTIVE_JOBS[job_id].get("total_stops")
        audio_files_in_zip = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                audio_files_in_zip = [
                    n for n in zip_ref.namelist()
                    if re.fullmatch(r'audio_\d+\.mp3', n)
                ]
            actual_stops = len(audio_files_in_zip)
        except Exception as count_err:
            print(f"WARNING: Could not verify stop count in ZIP: {count_err}")
            actual_stops = None
        
        print(f"STOP COUNT VERIFICATION: expected={expected_stops}, actual={actual_stops}, files={sorted(audio_files_in_zip)}")
        ACTIVE_JOBS[job_id]["expected_stops"] = expected_stops
        ACTIVE_JOBS[job_id]["actual_stops"] = actual_stops
        
        if actual_stops == 0 or actual_stops is None:
            error_msg = (
                f"Tour generation produced no audio files. "
                f"Expected {expected_stops} stops, got {actual_stops}. Job {job_id}."
            )
            print(f"ERROR: {error_msg}")
            ACTIVE_JOBS[job_id]["status"] = "error"
            ACTIVE_JOBS[job_id]["error"] = error_msg
            try:
                os.remove(zip_path)
            except Exception:
                pass
            return  # Do not store in database, do not trigger translation
        elif actual_stops is not None and actual_stops != expected_stops:
            warning_msg = (
                f"STOP COUNT MISMATCH: requested {expected_stops} stops, "
                f"delivered {actual_stops}. Job {job_id}."
            )
            print(f"ERROR: {warning_msg}")
            ACTIVE_JOBS[job_id]["stop_count_warning"] = warning_msg
        
        # Step 5: Store in database with original tour content
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 5/5: Storing modernized tour in database...")
        tour_name = f"{location} - {tour_type} Tour"
        
        # Extract coordinates
        lat = None
        lng = None
        if coordinates and len(coordinates) >= 2:
            lat = coordinates[0]
            lng = coordinates[1]
        
        # Read original tour content from the text file for translation purposes
        tour_content = None
        if tour_file:
            tour_file_path = os.path.join(TOURS_DIR, tour_file)
            if os.path.exists(tour_file_path):
                try:
                    with open(tour_file_path, 'r', encoding='utf-8') as f:
                        tour_content = f.read()
                    print(f"Successfully read tour content: {len(tour_content)} characters")
                    
                    # Also add tour_content.txt to the ZIP file for redundancy
                    try:
                        with zipfile.ZipFile(zip_path, 'a') as zipf:
                            zipf.writestr('tour_content.txt', tour_content.encode('utf-8'))
                        print(f"Added tour_content.txt to ZIP file")
                    except Exception as zip_error:
                        print(f"Warning: Could not add tour_content.txt to ZIP: {zip_error}")
                        
                except Exception as read_error:
                    print(f"Warning: Could not read tour content from {tour_file_path}: {read_error}")
            else:
                print(f"Warning: Tour file not found: {tour_file_path}")
        else:
            print(f"Warning: No tour file available for content extraction")
        
        # Store in database with tour content
        store_success = store_audio_tour(tour_name, request_string or location, zip_path, lat, lng, tour_content)
        
        if store_success:
            print(f"Tour stored successfully with coordinates: lat={lat}, lng={lng}")
            
            # Get the tour ID from database (always needed for final_tour_id)
            english_tour_id = None
            try:
                import psycopg2
                conn = psycopg2.connect(
                    host=os.getenv('DB_HOST', 'postgres-2'),
                    database=os.getenv('DB_NAME', 'audiotours'),
                    user=os.getenv('DB_USER', 'admin'),
                    password=os.getenv('DB_PASSWORD', 'password123'),
                    port=os.getenv('DB_PORT', '5432')
                )
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM audio_tours WHERE tour_name = %s AND request_string = %s ORDER BY id DESC LIMIT 1",
                    (tour_name, request_string or location)
                )
                result = cur.fetchone()
                if result:
                    english_tour_id = result[0]
                    print(f"English tour ID: {english_tour_id}")
                cur.close()
                conn.close()
            except Exception as db_error:
                print(f"Warning: Could not get tour ID from database: {db_error}")
            if language != 'en':
                pass  # translation block below handles non-English
            
            # If non-English language requested, translate the tour
            if language != 'en' and english_tour_id:
                print(f"\n==== TRANSLATING TOUR TO {language.upper()} ====")
                try:
                    translation_data = {
                        "content_id": english_tour_id,
                        "content_type": "tour",
                        "languages": [language]
                    }
                    
                    print(f"Calling translation service with data: {translation_data}")
                    translation_response = requests.post(
                        f"{TRANSLATION_URL}/translate-with-audio",
                        headers={"Content-Type": "application/json"},
                        json=translation_data,
                        timeout=120
                    )
                    
                    if translation_response.status_code == 200:
                        translation_result = translation_response.json()
                        translated_tour_id = translation_result.get('translated_tour_ids', {}).get(language)
                        
                        if translated_tour_id:
                            print(f"Translation successful! Translated tour ID: {translated_tour_id}")
                            ACTIVE_JOBS[job_id]["translated_tour_id"] = translated_tour_id
                            ACTIVE_JOBS[job_id]["final_tour_id"] = translated_tour_id
                        else:
                            print(f"Warning: Translation completed but no tour ID returned")
                            ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id
                    else:
                        print(f"Translation failed: {translation_response.status_code} - {translation_response.text}")
                        ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id
                        
                except Exception as translation_error:
                    print(f"Translation error: {translation_error}")
                    ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id
            else:
                ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id or "unknown"
            
            # Update tour_requests status to completed
            if user_id and 'tour_id' in ACTIVE_JOBS[job_id]:
                tour_id = ACTIVE_JOBS[job_id]['tour_id']
                print(f"Updating tour_requests status for tour_id: {tour_id}")
                try:
                    update_data = {
                        'tour_id': tour_id,
                        'status': 'completed',
                        'finished_at': datetime.now().isoformat()
                    }
                    update_response = requests.post(
                        f"{TOUR_UPDATE_URL}/update",
                        headers={"Content-Type": "application/json"},
                        json=update_data,
                        timeout=10
                    )
                    if update_response.status_code == 200:
                        print(f"Successfully updated tour_requests status for {tour_id}")
                    else:
                        print(f"Failed to update tour_requests status: {update_response.text}")
                except Exception as update_error:
                    print(f"Error updating tour_requests status: {update_error}")
            else:
                print(f"No tour_id available for tour_requests update (user_id: {user_id})")
            
            # Clean up extraction directory after successful database storage
            # ZIP file is now the primary storage, directory is no longer needed
            if os.path.exists(extract_path):
                try:
                    print(f"Cleaning up extraction directory: {extract_path}")
                    shutil.rmtree(extract_path)
                    print(f"Successfully cleaned up directory: {extract_dir}")
                    print(f"Storage optimization: Directory removed, ZIP file remains as primary storage")
                except Exception as cleanup_error:
                    print(f"Warning: Could not clean up extraction directory: {cleanup_error}")
                    print(f"Directory will remain: {extract_path}")
            else:
                print(f"Extraction directory not found for cleanup: {extract_path}")
        else:
            print("Failed to store tour in database")
            print(f"Keeping extraction directory due to database storage failure: {extract_path}")
        
        # Complete
        final_message = f"Tour generation completed in {language.upper()}!"
        if language != 'en' and 'translated_tour_id' in ACTIVE_JOBS[job_id]:
            final_message += f" Translated tour ID: {ACTIVE_JOBS[job_id]['translated_tour_id']}"
        
        log_job_update(job_id, "completed", final_message)
        ACTIVE_JOBS[job_id]["netlify_ready"] = True
        ACTIVE_JOBS[job_id]["language"] = language
        if coordinates:
            ACTIVE_JOBS[job_id]["coordinates"] = coordinates
        
        print(f"==== ORCHESTRATE_TOUR_ASYNC COMPLETED: {datetime.now().isoformat()} ====")
        
    except Exception as e:
        print(f"\n==== EXCEPTION IN ORCHESTRATE_TOUR_ASYNC: {datetime.now().isoformat()} ====")
        print(f"Exception: {e}")
        print(f"Exception type: {type(e).__name__}")
        print(f"Traceback: {traceback.format_exc()}")
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)

def track_user_tour(user_id, tour_id, request_string):
    """Track a user's tour request in the user tracking service."""
    print(f"\n==== TRACKING USER TOUR: {datetime.now().isoformat()} ====")
    print(f"User ID: {user_id}")
    print(f"Tour ID: {tour_id}")
    print(f"Request string: {request_string}")
    
    try:
        # Prepare data for the user tracking service
        payload = {
            "tour_request": {
                "tour_id": tour_id,
                "request_string": request_string
            }
        }
        
        # Call the user tracking service
        print(f"Calling user tracking API for user {user_id}")
        print(f"Payload: {payload}")
        
        response = requests.put(
            f"{USER_API_URL}/user/{user_id}",
            json=payload,
            timeout=10
        )
        
        print(f"User tracking response: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            print(f"ERROR: Failed to track user tour: {response.text}")
            return False
        
        print(f"SUCCESS: User tour tracked successfully")
        return True
    except Exception as e:
        print(f"ERROR: Exception tracking user tour: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

def get_coordinates_direct(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    print(f"\n==== DIRECT COORDINATES REQUEST FOR: {location} ====")
    print(f"Time: {datetime.now().isoformat()}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service (internal port 5004)
        url = f"{COORDINATES_URL}/coordinates/{encoded_location}"
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
        return (0, 0)  # Return 0,0 as fallback

# Direct function to call coordinates-fromai service
def call_coordinates_service(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    print(f"\n==== DIRECT CALL TO COORDINATES-FROMAI SERVICE ====")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Location: {location}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service
        url = f"{COORDINATES_URL}/coordinates/{encoded_location}"
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
        return None

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "tour_orchestrator"})

@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    """Generate a complete tour from text to audio to web."""
    print(f"\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")
    sys.stdout.flush()
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data(as_text=True)}")
    print(f"Request JSON: {request.json if request.is_json else None}")
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.json
    print(f"Received request data: {data}")
    
    location = sanitize_input(data.get('location'))
    tour_type = sanitize_input(data.get('tour_type'))
    total_stops = data.get('total_stops', 10)
    user_id = sanitize_input(data.get('user_id'))
    request_string = sanitize_input(data.get('request_string'))
    language = data.get('language', 'en')  # Default to English
    
    print(f"Extracted parameters:")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  total_stops: {total_stops}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")
    print(f"  language: {language}")
    
    # Validate language parameter
    supported_languages = ['en', 'ru', 'es', 'fr', 'de', 'zh']
    if language not in supported_languages:
        return jsonify({"error": f"Unsupported language: {language}. Supported: {supported_languages}"}), 400
    
    if not location or not tour_type:
        return jsonify({"error": "location and tour_type are required"}), 400
    
    try:
        total_stops = int(total_stops)
        if total_stops < 1 or total_stops > 50:
            return jsonify({"error": "total_stops must be between 1 and 50"}), 400
    except ValueError:
        return jsonify({"error": "total_stops must be a valid integer"}), 400
    
    # Entitlements check: verify user hasn't exceeded their plan limits
    if user_id:
        try:
            from entitlements import check_tour_quota
            quota = check_tour_quota(user_id, total_stops)
            if not quota['allowed']:
                print(f"[QUOTA] Denied tour for {user_id}: {quota}")
                return jsonify(quota), 429
            # Clamp stops to plan maximum
            total_stops = quota['clamped_stops']
            print(f"[QUOTA] Allowed for {user_id}: used={quota['used']}, remaining={quota['remaining']}, stops_clamped={total_stops}")
        except Exception as quota_err:
            print(f"[QUOTA] Error checking quota (allowing): {quota_err}")
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    print(f"Generated job ID: {job_id}")
    sys.stdout.flush()
    
    # Initialize job tracking
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for processing",
        "location": location,
        "tour_type": tour_type,
        "total_stops": total_stops,
        "user_id": user_id,
        "request_string": request_string,
        "language": language,
        "created_at": datetime.now().isoformat()
    }
    
    # Track user request immediately
    print(f"Checking user tracking condition - user_id: '{user_id}', request_string: '{request_string}'")
    if user_id and request_string:
        try:
            tour_id = f"tour_{job_id[:8]}"
            print(f"Tracking user tour immediately - User: {user_id}, Tour: {tour_id}")
            track_user_tour(user_id, tour_id, request_string)
            ACTIVE_JOBS[job_id]["tour_id"] = tour_id
            print(f"User tour tracking completed successfully")
        except Exception as e:
            print(f"ERROR: Failed to track user tour: {e}")
            print(f"Traceback: {traceback.format_exc()}")
    else:
        print(f"User tracking skipped - user_id empty: {not user_id}, request_string empty: {not request_string}")
    
    # Start orchestration in background thread
    print(f"Starting orchestration in background thread")
    sys.stdout.flush()
    thread = threading.Thread(
        target=orchestrate_tour_async,
        args=(job_id, location, tour_type, total_stops, user_id, request_string, language)
    )
    thread.daemon = True
    thread.start()
    
    print(f"Returning response: job_id={job_id}, status=queued, language={language}")
    sys.stdout.flush()
    return jsonify({"job_id": job_id, "status": "queued", "language": language})

@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status."""
    print(f"\n==== STATUS REQUEST: {datetime.now().isoformat()} ====")
    print(f"Job ID: {job_id}")
    
    if job_id not in ACTIVE_JOBS:
        print(f"Job not found: {job_id}")
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
        if "final_tour_id" in job:
            response["final_tour_id"] = job["final_tour_id"]
        if "translated_tour_id" in job:
            response["translated_tour_id"] = job["translated_tour_id"]
        if "expected_stops" in job:
            response["expected_stops"] = job["expected_stops"]
        if "actual_stops" in job:
            response["actual_stops"] = job["actual_stops"]
        if "stop_count_warning" in job:
            response["stop_count_warning"] = job["stop_count_warning"]
    elif job["status"] == "error":
        response["error"] = job["error"]
    
    print(f"Returning status: {response}")
    return jsonify(response)


@app.route('/tour-status', methods=['POST'])
def update_tour_status():
    """K1: REST endpoint for mobile app to update tour request status.
    Replaces the client-side raw SQL direct DB update.
    
    Request body:
        {
            "tour_id": "tour_19e73f4059d",    (required)
            "status": "completed|failed|started",  (required)
            "job_id": "uuid"                  (optional, for correlation)
        }
    Response:
        {"status": "success", "tour_id": "...", "rows_affected": 1}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "JSON body required"}), 400
        
        tour_id = data.get('tour_id')
        new_status = data.get('status')
        
        if not tour_id or not new_status:
            return jsonify({"status": "error", "message": "tour_id and status are required"}), 400
        
        # Validate status value
        allowed_statuses = ('started', 'completed', 'failed', 'processing')
        if new_status not in allowed_statuses:
            return jsonify({"status": "error", "message": f"status must be one of: {allowed_statuses}"}), 400
        
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        
        if new_status == 'completed':
            cur.execute(
                "UPDATE tour_requests SET status = %s, finished_at = NOW() WHERE tour_id = %s",
                (new_status, tour_id)
            )
        else:
            cur.execute(
                "UPDATE tour_requests SET status = %s WHERE tour_id = %s",
                (new_status, tour_id)
            )
        
        rows_affected = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"[TOUR-STATUS] Updated tour_id={tour_id} to status={new_status}, rows={rows_affected}")
        return jsonify({"status": "success", "tour_id": tour_id, "rows_affected": rows_affected})
    
    except Exception as e:
        print(f"[TOUR-STATUS] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download/<job_id>', methods=['GET'])
def download_tour(job_id):
    """Download the complete tour package."""
    print(f"\n==== DOWNLOAD REQUEST: {datetime.now().isoformat()} ====")
    print(f"Job ID: {job_id}")
    
    # First try to find in active jobs (for recently generated tours)
    if job_id in ACTIVE_JOBS:
        job = ACTIVE_JOBS[job_id]
        if job["status"] != "completed":
            print(f"Job not completed: {job_id}")
            return jsonify({"error": "Job not completed"}), 400
        
        zip_path = os.path.join(TOURS_DIR, job["output_zip"])
        if os.path.exists(zip_path):
            # Sanitize filename by removing newlines and other problematic characters
            safe_filename = job["output_zip"].replace('\n', '_').replace('\r', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
            
            print(f"Sending file from active jobs: {zip_path}")
            return send_file(zip_path, as_attachment=True, attachment_filename=safe_filename)
    
    # Try to find in database (for translated tours or older tours)
    try:
        tour_id = int(job_id)
        print(f"Looking for tour ID {tour_id} in database")
        
        import psycopg2
        import io
        
        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        
        # Get tour from database
        cur.execute(
            "SELECT tour_name, audio_tour FROM audio_tours WHERE id = %s",
            (tour_id,)
        )
        result = cur.fetchone()
        
        if result:
            tour_name, zip_data = result
            print(f"Found tour in database: {tour_name}")
            print(f"ZIP data size: {len(zip_data)} bytes")
            
            # Create a safe filename
            safe_filename = f"tour_{tour_id}.zip"
            
            # Create BytesIO object from the binary data
            zip_buffer = io.BytesIO(zip_data)
            zip_buffer.seek(0)
            
            print(f"Sending tour from database: {safe_filename}")
            
            # Close database connection
            cur.close()
            conn.close()
            
            return send_file(
                zip_buffer,
                as_attachment=True,
                attachment_filename=safe_filename,
                mimetype='application/zip'
            )
        else:
            print(f"Tour ID {tour_id} not found in database")
            cur.close()
            conn.close()
            return jsonify({"error": "Tour not found"}), 404
            
    except ValueError:
        # job_id is not a number, only check active jobs
        print(f"Job ID is not numeric: {job_id}")
        return jsonify({"error": "Job not found"}), 404
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"error": "Database error"}), 500

@app.route('/serve/<job_id>', methods=['GET'])
def serve_tour_info(job_id):
    """Get information about serving the tour."""
    print(f"\n==== SERVE REQUEST: {datetime.now().isoformat()} ====")
    print(f"Job ID: {job_id}")
    
    if job_id not in ACTIVE_JOBS:
        print(f"Job not found: {job_id}")
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        print(f"Job not completed: {job_id}")
        return jsonify({"error": "Job not completed"}), 400
    
    extract_path = os.path.join(TOURS_DIR, job["extract_dir"])
    if not os.path.exists(extract_path):
        print(f"Tour directory not found: {extract_path}")
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
    
    print(f"Returning serve info: {response}")
    return jsonify(response)

@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all orchestration jobs."""
    print(f"\n==== LIST JOBS REQUEST: {datetime.now().isoformat()} ====")
    
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
    
    print(f"Returning {len(jobs)} jobs")
    return jsonify({"jobs": jobs})

if __name__ == '__main__':
    # Ensure tours directory exists
    ensure_tours_directory()
    
    print(f"Starting Modified Tour Orchestrator Service: {datetime.now().isoformat()}")
    print(f"Tours directory: {TOURS_DIR}")
    print(f"Pipeline: Complete tour generation orchestration with database storage")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5002')), debug=False)