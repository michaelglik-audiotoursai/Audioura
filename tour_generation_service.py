"""
REST API service for processing tour text files into deployable Netlify directories.
Runs the complete pipeline: text_to_index -> single_file_app_builder -> prepare_for_netlify
"""
# Version synchronization with mobile app
SERVICE_VERSION = "1.1.19"

import os
import sys
import json
import uuid
import zipfile
import shutil
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading
import tempfile

# Import the existing scripts
from text_to_index_fixed import main as text_to_index_main
from single_file_app_builder import create_single_file_app
from prepare_for_netlify import prepare_for_netlify

app = Flask(__name__)
CORS(app)

# Global variables
TOURS_DIR = "/app/tours"  # Docker volume mount point
ACTIVE_JOBS = {}  # Track running jobs

def ensure_tours_directory():
    """Ensure the tours directory exists."""
    if not os.path.exists(TOURS_DIR):
        os.makedirs(TOURS_DIR)

def process_tour_async(job_id, tour_file_path):
    """Process tour file asynchronously through the complete pipeline."""
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = "Starting tour processing pipeline..."
        
        # Get the base filename without extension
        tour_filename = os.path.basename(tour_file_path)
        tour_name = os.path.splitext(tour_filename)[0]
        
        # Create unique working directory for this job to avoid conflicts
        job_work_dir = os.path.join(TOURS_DIR, f"job_{job_id}")
        os.makedirs(job_work_dir, exist_ok=True)
        
        # Copy the tour file to the job working directory
        import shutil
        job_tour_file = os.path.join(job_work_dir, tour_filename)
        shutil.copy2(tour_file_path, job_tour_file)
        
        print(f"DEBUG: Copied {tour_file_path} to {job_tour_file}")
        print(f"DEBUG: Job working directory: {job_work_dir}")
        print(f"DEBUG: Files in job dir: {os.listdir(job_work_dir) if os.path.exists(job_work_dir) else 'DIR NOT FOUND'}")
        
        # Change to the job working directory for processing
        original_cwd = os.getcwd()
        os.chdir(job_work_dir)
        
        try:
            # Step 1: Run text_to_index.py
            ACTIVE_JOBS[job_id]["progress"] = "Step 1/3: Converting text to audio files and web page..."
            print(f"DEBUG: About to call text_to_index_main with: {tour_filename}")
            print(f"DEBUG: Current working directory: {os.getcwd()}")
            print(f"DEBUG: Files in current dir: {os.listdir('.')}")
            directory_name = text_to_index_main(tour_filename)
            ACTIVE_JOBS[job_id]["intermediate_dir"] = directory_name
            
            # Step 2: Run single_file_app_builder.py
            ACTIVE_JOBS[job_id]["progress"] = "Step 2/3: Creating single-file HTML app..."
            single_file_output = create_single_file_app(directory_name)
            single_file_name = f"{directory_name}_single_file.html"
            ACTIVE_JOBS[job_id]["single_file"] = single_file_name
            
            # Step 3: Run prepare_for_netlify.py
            ACTIVE_JOBS[job_id]["progress"] = "Step 3/3: Preparing for Netlify deployment..."
            netlify_dir = prepare_for_netlify(single_file_name)
            ACTIVE_JOBS[job_id]["netlify_dir"] = netlify_dir
            
            # Create a ZIP file of the Netlify directory
            ACTIVE_JOBS[job_id]["progress"] = "Creating deployment package..."
            zip_filename = f"{tour_name}_netlify_deploy_{job_id[:8]}.zip"
            zip_path = os.path.join(TOURS_DIR, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                netlify_path = os.path.join(job_work_dir, netlify_dir)
                for root, dirs, files in os.walk(netlify_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, netlify_path)
                        zipf.write(file_path, arcname)
            
            # Update job status
            ACTIVE_JOBS[job_id]["status"] = "completed"
            ACTIVE_JOBS[job_id]["progress"] = "Tour processing completed successfully!"
            ACTIVE_JOBS[job_id]["output_zip"] = zip_filename
            ACTIVE_JOBS[job_id]["netlify_ready"] = True
            
        finally:
            # Restore original working directory
            os.chdir(original_cwd)
            
            # Clean up job working directory after successful completion
            if job_id in ACTIVE_JOBS and ACTIVE_JOBS[job_id]["status"] == "completed":
                try:
                    import shutil
                    shutil.rmtree(job_work_dir)
                    print(f"Cleaned up job directory: {job_work_dir}")
                except Exception as cleanup_error:
                    print(f"Warning: Could not clean up job directory: {cleanup_error}")
            
    except Exception as e:
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)
        # Restore original working directory on error
        try:
            os.chdir(original_cwd)
        except:
            pass

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "tour_generation", "version": SERVICE_VERSION})

@app.route('/process', methods=['POST'])
def process_tour():
    """Process a tour file through the complete pipeline."""
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Get tour file parameter
    tour_file = data.get('tour_file')
    if not tour_file:
        return jsonify({"error": "tour_file parameter is required"}), 400
    
    # Check if tour file exists
    tour_file_path = os.path.join(TOURS_DIR, tour_file)
    if not os.path.exists(tour_file_path):
        return jsonify({"error": f"Tour file '{tour_file}' not found"}), 404
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job tracking
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for processing",
        "tour_file": tour_file,
        "created_at": datetime.now().isoformat()
    }
    
    # Start processing in background thread
    thread = threading.Thread(
        target=process_tour_async,
        args=(job_id, tour_file_path)
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
        "tour_file": job["tour_file"],
        "created_at": job["created_at"]
    }
    
    if job["status"] == "completed":
        response["output_zip"] = job["output_zip"]
        response["netlify_ready"] = job["netlify_ready"]
        response["intermediate_dir"] = job.get("intermediate_dir")
        response["single_file"] = job.get("single_file")
        response["netlify_dir"] = job.get("netlify_dir")
    elif job["status"] == "error":
        response["error"] = job["error"]
    
    return jsonify(response)

@app.route('/download/<job_id>', methods=['GET'])
def download_tour(job_id):
    """Download the Netlify-ready deployment package."""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed"}), 400
    
    zip_path = os.path.join(TOURS_DIR, job["output_zip"])
    if not os.path.exists(zip_path):
        return jsonify({"error": "File not found"}), 404
    
    # Clean up job working directory after download since ZIP contains everything needed
    job_work_dir = os.path.join(TOURS_DIR, f"job_{job_id}")
    if os.path.exists(job_work_dir):
        try:
            import shutil
            shutil.rmtree(job_work_dir)
            print(f"Cleaned up job directory after download: {job_work_dir}")
        except Exception as cleanup_error:
            print(f"Warning: Could not clean up job directory: {cleanup_error}")
    
    response = send_file(zip_path, as_attachment=True, download_name=job["output_zip"])
    response.headers['Content-Disposition'] = f'attachment; filename="{job["output_zip"]}"'
    return response

@app.route('/upload', methods=['POST'])
def upload_tour_file():
    """Upload a tour text file for processing."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.txt'):
        return jsonify({"error": "Only .txt files are allowed"}), 400
    
    # Save the uploaded file
    filename = file.filename
    file_path = os.path.join(TOURS_DIR, filename)
    file.save(file_path)
    
    return jsonify({
        "message": "File uploaded successfully",
        "filename": filename,
        "size": os.path.getsize(file_path)
    })

@app.route('/files', methods=['GET'])
def list_tour_files():
    """List all available tour files."""
    files = []
    if os.path.exists(TOURS_DIR):
        for filename in os.listdir(TOURS_DIR):
            if filename.endswith('.txt'):
                file_path = os.path.join(TOURS_DIR, filename)
                stat = os.stat(file_path)
                files.append({
                    "filename": filename,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
    
    return jsonify({"files": files})

@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all processing jobs."""
    jobs = []
    for job_id, job_data in ACTIVE_JOBS.items():
        jobs.append({
            "job_id": job_id,
            "status": job_data["status"],
            "tour_file": job_data["tour_file"],
            "created_at": job_data["created_at"],
            "progress": job_data.get("progress", "")
        })
    
    return jsonify({"jobs": jobs})

@app.route('/cleanup/files', methods=['DELETE'])
def cleanup_files():
    """Delete all uploaded tour files."""
    try:
        deleted_files = []
        if os.path.exists(TOURS_DIR):
            for filename in os.listdir(TOURS_DIR):
                if filename.endswith('.txt'):
                    file_path = os.path.join(TOURS_DIR, filename)
                    os.remove(file_path)
                    deleted_files.append(filename)
        
        return jsonify({
            "message": f"Deleted {len(deleted_files)} tour files",
            "deleted_files": deleted_files
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cleanup/outputs', methods=['DELETE'])
def cleanup_outputs():
    """Delete all generated ZIP files."""
    try:
        deleted_files = []
        if os.path.exists(TOURS_DIR):
            for filename in os.listdir(TOURS_DIR):
                if filename.endswith('.zip'):
                    file_path = os.path.join(TOURS_DIR, filename)
                    os.remove(file_path)
                    deleted_files.append(filename)
        
        return jsonify({
            "message": f"Deleted {len(deleted_files)} output files",
            "deleted_files": deleted_files
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cleanup/all', methods=['DELETE'])
def cleanup_all():
    """Delete all files and clear job history."""
    try:
        deleted_files = []
        if os.path.exists(TOURS_DIR):
            for filename in os.listdir(TOURS_DIR):
                file_path = os.path.join(TOURS_DIR, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_files.append(filename)
                elif os.path.isdir(file_path) and filename.startswith('job_'):
                    import shutil
                    shutil.rmtree(file_path)
                    deleted_files.append(f"{filename}/")
        
        # Clear job history
        global ACTIVE_JOBS
        job_count = len(ACTIVE_JOBS)
        ACTIVE_JOBS.clear()
        
        return jsonify({
            "message": f"Deleted {len(deleted_files)} files and cleared {job_count} jobs",
            "deleted_files": deleted_files
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete/file/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Delete a specific tour file or output file."""
    try:
        file_path = os.path.join(TOURS_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({"error": f"File '{filename}' not found"}), 404
        
        if not os.path.isfile(file_path):
            return jsonify({"error": f"'{filename}' is not a file"}), 400
        
        file_size = os.path.getsize(file_path)
        os.remove(file_path)
        
        return jsonify({
            "message": f"Deleted file '{filename}'",
            "size_freed_mb": round(file_size / (1024 * 1024), 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete/job/<job_id>', methods=['DELETE'])
def delete_job_directory(job_id):
    """Delete a specific job working directory."""
    try:
        job_work_dir = os.path.join(TOURS_DIR, f"job_{job_id}")
        if not os.path.exists(job_work_dir):
            return jsonify({"error": f"Job directory for '{job_id}' not found"}), 404
        
        if not os.path.isdir(job_work_dir):
            return jsonify({"error": f"'{job_id}' is not a valid job directory"}), 400
        
        # Calculate directory size before deletion
        total_size = 0
        for root, dirs, files in os.walk(job_work_dir):
            for file in files:
                total_size += os.path.getsize(os.path.join(root, file))
        
        import shutil
        shutil.rmtree(job_work_dir)
        
        return jsonify({
            "message": f"Deleted job directory '{job_id}'",
            "size_freed_mb": round(total_size / (1024 * 1024), 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/storage', methods=['GET'])
def get_storage_info():
    """Get storage usage information."""
    try:
        total_size = 0
        file_count = 0
        dir_count = 0
        txt_files = []
        zip_files = []
        job_dirs = []
        
        if os.path.exists(TOURS_DIR):
            for item in os.listdir(TOURS_DIR):
                item_path = os.path.join(TOURS_DIR, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    total_size += size
                    file_count += 1
                    if item.endswith('.txt'):
                        txt_files.append({"name": item, "size_mb": round(size / (1024 * 1024), 2)})
                    elif item.endswith('.zip'):
                        zip_files.append({"name": item, "size_mb": round(size / (1024 * 1024), 2)})
                elif os.path.isdir(item_path) and item.startswith('job_'):
                    dir_size = 0
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            dir_size += os.path.getsize(os.path.join(root, file))
                    total_size += dir_size
                    dir_count += 1
                    job_dirs.append({"name": item, "size_mb": round(dir_size / (1024 * 1024), 2)})
        
        return jsonify({
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "directory_count": dir_count,
            "active_jobs": len(ACTIVE_JOBS),
            "txt_files": txt_files,
            "zip_files": zip_files,
            "job_directories": job_dirs
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Ensure tours directory exists
    ensure_tours_directory()
    
    print(f"Starting Tour Generation Service...")
    print(f"Tours directory: {TOURS_DIR}")
    print(f"Pipeline: text_to_index -> single_file_app_builder -> prepare_for_netlify")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5001, debug=False)