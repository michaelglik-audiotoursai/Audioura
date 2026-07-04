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
import threading
import re

# Import the tour text generator
from generate_tour_text import generate_tour_text
import api_call_logger
from job_store import get_job_store
from storied_version_constants import STORIED_SERVICE_VERSION

SERVICE_VERSION = STORIED_SERVICE_VERSION

app = Flask(__name__)
CORS(app)

# Global variables
TOURS_DIR = "/app/tours"
ACTIVE_JOBS = get_job_store('tour-generator')

def ensure_tours_directory():
    """Ensure the tours directory exists."""
    if not os.path.exists(TOURS_DIR):
        os.makedirs(TOURS_DIR)

def generate_tour_async(job_id, location, tour_type, total_stops=10, user_id=None):
    """Generate tour text asynchronously."""
    try:
        api_call_logger.log("GENERATOR_SERVICE_ASYNC_START", {
            "job_id": job_id,
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops,
            "user_id": user_id,
        })
        
        ACTIVE_JOBS.update(job_id, status="processing", progress="Starting tour text generation...")

        # [S46] Persona lookup — graceful degradation if unavailable
        _persona_value = None
        if user_id:
            try:
                from persona_preference_store import get_persona
                from onboarding_preference import UserPersona
                _db_url = os.getenv('DATABASE_URL', 'postgresql://admin:admin@localhost:5432/audiotours')
                _persona_result = get_persona(user_id, _db_url)
                if _persona_result is not None:
                    _persona_value = _persona_result.value
                    print(f"  [S46] Persona for user '{user_id}': {_persona_value}")
                else:
                    print(f"  [S46] No persona stored for user '{user_id}' — using default")
            except Exception as e:
                print(f"  [S46] Persona lookup failed (graceful degradation): {e}")
                _persona_value = None
        
        # Create a temporary file for the output
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as temp_file:
            temp_path = temp_file.name
        
        api_call_logger.log("CALLING_GENERATE_TOUR_TEXT_FUNCTION", {
            "function": "generate_tour_text",
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops,
            "persona": _persona_value,
            "log_file": api_call_logger.get_log_path(),
        })
        
        # Generate the tour text - PASS total_stops and persona parameters
        tour_text, _, coordinates = generate_tour_text(location, tour_type, temp_path, total_stops, persona=_persona_value)
        
        if tour_text is None:
            ACTIVE_JOBS.update(job_id, status="error",
                              error=f"Tour generation failed for '{location}' — no stops could be generated (all filtered or knowledge insufficient).")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return
        
        # [BLOCKER4c] Factual QA gate — reject factually-broken tours in serving path
        if os.getenv('STORIED_MODE', 'false').lower() == 'true' and tour_text:
            try:
                import content_qa_runner
                content_qa_runner.PASS_COUNT = 0
                content_qa_runner.FAIL_COUNT = 0
                content_qa_runner.FACTUAL_FAIL_COUNT = 0
                content_qa_runner.run_qa(tour_text)
                if content_qa_runner.FACTUAL_FAIL_COUNT > 0:
                    print(f"[BLOCKER4c] FACTUAL QA FAILED ({content_qa_runner.FACTUAL_FAIL_COUNT} failures) — rejecting tour")
                    ACTIVE_JOBS.update(job_id, status="error",
                                      error=f"Tour failed factual integrity check ({content_qa_runner.FACTUAL_FAIL_COUNT} factual failures). Please try again.")
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    return
                else:
                    print(f"[BLOCKER4c] Factual QA passed ({content_qa_runner.PASS_COUNT}/11)")
            except ImportError:
                print(f"[BLOCKER4c] content_qa_runner not available — QA gate skipped")
            except SystemExit:
                # content_qa_runner calls sys.exit() — catch it in serving path
                if content_qa_runner.FACTUAL_FAIL_COUNT > 0:
                    print(f"[BLOCKER4c] FACTUAL QA FAILED (caught SystemExit) — rejecting tour")
                    ACTIVE_JOBS.update(job_id, status="error",
                                      error=f"Tour failed factual integrity check. Please try again.")
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    return
            except Exception as e:
                print(f"[BLOCKER4c] QA gate error (non-fatal): {e}")

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
        
        # Update job status — use .update() for database-mode compatibility
        tour_content_str = None
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                tour_content_str = f.read()
        except Exception as content_err:
            print(f"Warning: Could not read tour_content: {content_err}")
        
        ACTIVE_JOBS.update(job_id, status="completed",
                          progress="Tour text generation completed successfully!",
                          output_file=output_filename,
                          coordinates=coordinates,
                          **({"tour_content": tour_content_str} if tour_content_str else {}))
        
    except Exception as e:
        ACTIVE_JOBS.update(job_id, status="error", error=str(e))

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "tour_text_generator",
        "version": SERVICE_VERSION,
        "mode": os.getenv("STORIED_MODE", "false"),
    })

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
    user_id = data.get('user_id')  # [S46] Extract user_id for persona lookup
    
    api_call_logger.log("GENERATOR_SERVICE_RECEIVED_REQUEST", {
        "raw_request_body": data,
        "location": location,
        "tour_type": tour_type,
        "total_stops_raw": data.get('total_stops', '(not provided - will default to 10)'),
        "total_stops_resolved": total_stops,
    })
    
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
    
    # Start generation in background thread
    thread = threading.Thread(
        target=generate_tour_async,
        args=(job_id, location, tour_type, total_stops, user_id)
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
        if "tour_content" in job:
            response["tour_content"] = job["tour_content"]
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
    
    return send_file(output_path, as_attachment=True, download_name=job["output_file"])

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
    port = int(os.getenv('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=False)