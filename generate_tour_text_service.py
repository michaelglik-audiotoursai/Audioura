"""
Modified version of generate_tour_text_service.py that includes geo coordinates
"""
import os
import sys
import json
import time
import uuid
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Configure unbuffered logging
import sys
import traceback
sys.stdout.reconfigure(line_buffering=True)
print("\n==== TOUR GENERATOR SERVICE STARTING ====")
print(f"Time: {datetime.now().isoformat()}")
sys.stdout.flush()
import threading
import re

# Import the modified tour text generator
from modified_generate_tour_text import generate_tour_text

app = Flask(__name__)
CORS(app)

# Global variables
TOURS_DIR = "/app/tours"
ACTIVE_JOBS = {}

def ensure_tours_directory():
    """Ensure the tours directory exists."""
    if not os.path.exists(TOURS_DIR):
        os.makedirs(TOURS_DIR)

def generate_tour_async(job_id, location, tour_type, total_stops=10):
    """Generate tour text asynchronously."""
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = "Starting tour text generation..."
        
        # Create a temporary file for the output
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as temp_file:
            temp_path = temp_file.name
        
        # Generate the tour text
        print(f"location: {location} MVG")
        print(f"tour_type: {tour_type}")
        print(f"temp_path: {temp_path}")
        print(f"total_stops: {total_stops}")
        sys.stdout.flush()
        tour_text, _, coordinates = generate_tour_text(location, tour_type, temp_path, total_stops)
        
        # Create a safe filename for the output
        safe_location = ''.join(c if c.isalnum() else '_' for c in location)
        safe_tour_type = ''.join(c if c.isalnum() else '_' for c in tour_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{safe_location}_{safe_tour_type}_tour_{timestamp}.txt"
        output_path = os.path.join(TOURS_DIR, output_filename)
        
        # Copy the temporary file to the output path
        import shutil
        shutil.copy2(temp_path, output_path)
        
        # Clean up the temporary file
        os.unlink(temp_path)
        
        # Update job status
        ACTIVE_JOBS[job_id]["status"] = "completed"
        ACTIVE_JOBS[job_id]["progress"] = "Tour text generation completed successfully!"
        ACTIVE_JOBS[job_id]["output_file"] = output_filename
        ACTIVE_JOBS[job_id]["coordinates"] = coordinates
        
    except Exception as e:
        print(f"==== EXCEPTION IN generate_tour_async: {datetime.now().isoformat()} ====MVG^")
        print(f"Exception: {e}")
        print(f"Exception type: {type(e).__name__}")
        print(f"Traceback: {traceback.format_exc()}")
        sys.stdout.flush()
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "tour_text_generator"})

@app.route('/generate', methods=['POST'])
def generate_tour():
    """Generate tour text."""
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Get parameters
    location = data.get('location')
    tour_type = data.get('tour_type')
    total_stops = data.get('total_stops', 10)
    
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
        "created_at": datetime.now().isoformat()
    }
    print(f'ACTIVE_JOBS[{job_id}] = {json.dumps(ACTIVE_JOBS[job_id], indent=4)} MVG^')
    sys.stdout.flush()
    
    thread = threading.Thread(
        target=generate_tour_async,
        args=(job_id, location, tour_type, total_stops)
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
        response["output_file"] = job["output_file"]
        if "coordinates" in job:
            response["coordinates"] = job["coordinates"]
    elif job["status"] == "error":
        response["error"] = job["error"]
    
    return jsonify(response)

@app.route('/download/<job_id>', methods=['GET'])
def download_tour(job_id):
    """Download the generated tour text."""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed"}), 400
    
    output_path = os.path.join(TOURS_DIR, job["output_file"])
    if not os.path.exists(output_path):
        return jsonify({"error": "File not found"}), 404
    attachmment_filleme_parameter=job["output_file"]
    print(f"Sending file: {output_path} MVG^")
    if attachmment_filleme_parameter:
        print(f"job[\"output_file\"] as attachment_filename: {attachmment_filleme_parameter} MVG^")
    return send_file(output_path, as_attachment=True, attachment_filename=job["output_file"])

@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all generation jobs."""
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

if __name__ == '__main__':
    # Ensure tours directory exists
    ensure_tours_directory()
    
    print(f"Starting Modified Tour Text Generator Service...")
    print(f"Tours directory: {TOURS_DIR}")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)