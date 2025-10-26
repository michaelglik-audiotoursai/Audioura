#!/usr/bin/env python3
"""
Script to add early logging to catch all requests
"""

def main():
    print("Adding early logging to catch all requests...")
    
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Add logging to the very beginning of the file
    content = """import os
import sys
import json
import uuid
import zipfile
import shutil
import time
import threading
import requests
import traceback
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Configure logging to be unbuffered
sys.stdout.reconfigure(line_buffering=True)
print("\\n==== TOUR ORCHESTRATOR SERVICE STARTING ====")
print(f"Time: {datetime.now().isoformat()}")

app = Flask(__name__)
CORS(app)

# Log all incoming requests at the middleware level
@app.before_request
def log_request():
    print("\\n==== INCOMING REQUEST AT MIDDLEWARE LEVEL ====")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote Address: {request.remote_addr}")
    print(f"User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    print(f"Content Type: {request.headers.get('Content-Type', 'Unknown')}")
    print(f"Content Length: {request.headers.get('Content-Length', 'Unknown')}")
    sys.stdout.flush()  # Force flush to ensure logs are written immediately

""" + content.split("import os", 1)[1]
    
    # Update the generate_complete_tour function to add more visible logging
    old_function_start = """@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    """Generate a complete tour from text to audio to web."""
    print(f"\\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")"""
    
    new_function_start = """@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    """Generate a complete tour from text to audio to web."""
    print("\\n")
    print("*" * 80)
    print(f"**** MOBILE APP CONNECTION DETECTED: {datetime.now().isoformat()} ****")
    print(f"**** Remote Address: {request.remote_addr} ****")
    print(f"**** User Agent: {request.headers.get('User-Agent', 'Unknown')} ****")
    print("*" * 80)
    print("\\n")
    sys.stdout.flush()  # Force flush to ensure logs are written immediately"""
    
    content = content.replace(old_function_start, new_function_start)
    
    # Write the file
    with open("tour_orchestrator_service.py", "w") as f:
        f.write(content)
    
    print("Done! Added early logging to catch all requests.")

if __name__ == "__main__":
    main()