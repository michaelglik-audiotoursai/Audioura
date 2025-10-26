"""
Modernized Tour Generation Service - Separate MP3/TXT Files
Implements REQ-001: Tour ZIP Structure Modernization
"""
SERVICE_VERSION = "1.2.5.176"

import os
import json
import uuid
import zipfile
import base64
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading

app = Flask(__name__)
CORS(app)

TOURS_DIR = "/app/tours"
ACTIVE_JOBS = {}

def create_modernized_tour_zip(tour_data, job_id):
    """Create tour ZIP with separate MP3 and TXT files"""
    tour_name = tour_data.get('tour_name', f'tour_{job_id[:8]}')
    zip_filename = f"{tour_name}_{job_id[:8]}.zip"
    zip_path = os.path.join(TOURS_DIR, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Generate HTML with external audio references
        html_content = generate_html_with_external_audio(tour_data)
        zipf.writestr('index.html', html_content)
        
        # Add separate MP3 files
        for stop_number, audio_data in enumerate(tour_data.get('audio_files', []), 1):
            if isinstance(audio_data, str):  # base64 encoded
                try:
                    audio_bytes = base64.b64decode(audio_data)
                except:
                    # If not valid base64, treat as raw bytes
                    audio_bytes = audio_data.encode('utf-8')
            else:
                audio_bytes = audio_data
            zipf.writestr(f'audio_{stop_number}.mp3', audio_bytes)
        
        # Add text files for editing
        for stop_number, text_content in enumerate(tour_data.get('text_content', []), 1):
            zipf.writestr(f'audio_{stop_number}.txt', text_content.encode('utf-8'))
        
        # Add PWA files
        zipf.writestr('manifest.json', generate_manifest(tour_name))
        zipf.writestr('service-worker.js', generate_service_worker())
    
    return zip_filename

def generate_html_with_external_audio(tour_data):
    """Generate HTML that references external MP3 files"""
    tour_name = tour_data.get('tour_name', 'Audio Tour')
    stops = tour_data.get('text_content', [])
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{tour_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .audio-item {{ margin: 20px 0; padding: 15px; border: 1px solid #ccc; }}
        audio {{ width: 100%; }}
    </style>
</head>
<body>
    <h1>{tour_name.replace('_', ' ').title()}</h1>'''
    
    for i, text in enumerate(stops, 1):
        # Extract stop title from text content
        lines = text.split('\n')
        stop_title = lines[0].strip() if lines else f"Stop {i}"
        
        html += f'''
    <div class="audio-item">
        <h3>{stop_title}: Audio {i}</h3>
        <audio id="audio-{i-1}" controls preload="metadata">
            <source src="audio_{i}.mp3" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
    </div>'''
    
    # Add the voice control JavaScript from build_web_page_fixed.py
    html += '''
    
    <script>
        let audioElements = [];
        let currentStopIndex = 0;
        let wasPlayingBeforeVoice = false;
        
        // Core audio control - always call this to play current audio
        window.playAudio = function() {
            // Stop all other audio first
            audioElements.forEach((audio, index) => {
                if (index !== currentStopIndex) {
                    audio.pause();
                    audio.currentTime = 0;
                }
            });
            
            // Play current audio
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].play();
                return "Success: Playing stop-" + currentStopIndex;
            }
            return "Error: No audio to play";
        };
        
        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return "Success: Audio paused";
            }
            return "Error: No audio to pause";
        };
        
        // Pause for voice recognition
        window.pauseAllAudio = function() {
            wasPlayingBeforeVoice = false;
            if (audioElements[currentStopIndex] && !audioElements[currentStopIndex].paused) {
                wasPlayingBeforeVoice = true;
                audioElements[currentStopIndex].pause();
            }
            return "Success: Audio paused for voice recognition";
        };
        
        // Navigation - just change pointer, don't play
        window.nextStop = function() {
            if (currentStopIndex < audioElements.length - 1) {
                currentStopIndex++;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at last stop";
        };
        
        window.previousStop = function() {
            if (currentStopIndex > 0) {
                currentStopIndex--;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at first stop";
        };
        
        // Reset current audio to beginning
        window.repeatStop = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].currentTime = 0;
                return "Success: Reset stop-" + currentStopIndex + " to beginning";
            }
            return "Error: No audio to reset";
        };
        
        // Seek forward/backward in current audio with bounds checking
        window.seekForward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime + seconds;
                const maxTime = audio.duration || 0;
                
                if (newTime >= maxTime) {
                    audio.currentTime = maxTime - 1; // 1 second before end
                    return "Success: Moved to near end (" + seconds + "s would exceed duration)";
                } else {
                    audio.currentTime = newTime;
                    return "Success: Moved forward " + seconds + " seconds";
                }
            }
            return "Error: No audio to seek";
        };
        
        window.seekBackward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime - seconds;
                
                if (newTime < 0) {
                    audio.currentTime = 0; // Beginning of audio
                    return "Success: Moved to beginning (" + seconds + "s would go below 0)";
                } else {
                    audio.currentTime = newTime;
                    return "Success: Moved backward " + seconds + " seconds";
                }
            }
            return "Error: No audio to seek";
        };
        
        window.initializeAudio = function() {
            return "Success: Audio system initialized with " + audioElements.length + " stops";
        };
        
        // Initialize audio elements array
        document.addEventListener('DOMContentLoaded', function() {
            const audios = document.querySelectorAll('audio');
            audioElements = Array.from(audios);
            
            // Track current playing audio
            audioElements.forEach((audio, index) => {
                audio.addEventListener('play', function() {
                    currentStopIndex = index;
                });
            });
        });
    </script>
</body>
</html>'''
    return html

def generate_manifest(tour_name):
    """Generate PWA manifest"""
    return json.dumps({
        "name": tour_name,
        "short_name": tour_name[:12],
        "start_url": "/",
        "display": "standalone",
        "background_color": "#2c3e50",
        "theme_color": "#2c3e50",
        "icons": []
    }, indent=2)

def generate_service_worker():
    """Generate service worker for offline functionality"""
    return '''
const CACHE_NAME = 'tour-cache-v1';
const urlsToCache = [
  '/',
  '/index.html'
];

// Cache audio and text files dynamically
self.addEventListener('fetch', function(event) {
  if (event.request.url.includes('.mp3') || event.request.url.includes('.txt')) {
    event.respondWith(
      caches.open(CACHE_NAME).then(function(cache) {
        return cache.match(event.request).then(function(response) {
          return response || fetch(event.request).then(function(response) {
            cache.put(event.request, response.clone());
            return response;
          });
        });
      })
    );
  }
});

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        return cache.addAll(urlsToCache);
      })
  );
});
'''

def generate_modernized_tour_async(job_id, tour_file_path):
    """Generate modernized tour from existing tour text file"""
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = "Processing tour text file..."
        
        # Read the tour text file
        with open(tour_file_path, 'r', encoding='utf-8') as f:
            tour_content = f.read()
        
        # Parse the tour content using the same logic as the working system
        ACTIVE_JOBS[job_id]["progress"] = "Parsing tour content..."
        modernized_data = parse_tour_content_to_modernized(tour_content)
        
        # Generate audio using TTS service
        ACTIVE_JOBS[job_id]["progress"] = "Generating audio files..."
        audio_files = []
        for i, text_content in enumerate(modernized_data["text_content"], 1):
            try:
                # Call Polly TTS service
                tts_response = requests.post(
                    "http://polly-tts-1:5018/synthesize",
                    headers={"Content-Type": "application/json"},
                    json={"text": text_content, "voice": "Joanna"},
                    timeout=30
                )
                
                if tts_response.status_code == 200:
                    audio_data = tts_response.content
                    audio_files.append(audio_data)
                else:
                    # Fallback to placeholder if TTS fails
                    audio_files.append(base64.b64encode(f"Audio for stop {i}".encode()).decode())
            except Exception as tts_error:
                print(f"TTS error for stop {i}: {tts_error}")
                audio_files.append(base64.b64encode(f"Audio for stop {i}".encode()).decode())
        
        modernized_data["audio_files"] = audio_files
        
        # Step 3: Create modernized ZIP
        ACTIVE_JOBS[job_id]["progress"] = "Creating modernized tour ZIP..."
        zip_filename = create_modernized_tour_zip(modernized_data, job_id)
        
        ACTIVE_JOBS[job_id]["status"] = "completed"
        ACTIVE_JOBS[job_id]["progress"] = "Modernized tour created successfully!"
        ACTIVE_JOBS[job_id]["output_zip"] = zip_filename
        ACTIVE_JOBS[job_id]["modernized"] = True
        
    except Exception as e:
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)

def parse_tour_content_to_modernized(tour_content):
    """Parse tour text content into modernized structure"""
    import re
    
    # Extract tour name from content
    tour_name_match = re.search(r'Step-by-Step Audio Guided Tour: (.+?)\n', tour_content)
    tour_name = tour_name_match.group(1) if tour_name_match else "Audio Tour"
    
    # Split content by stops
    stops = re.split(r'\n\s*Stop\s+(\d+):', tour_content)
    
    text_content = []
    
    if len(stops) > 1:
        stops = stops[1:]  # Remove title part
        
        # Process stops in pairs (number, content)
        for i in range(0, len(stops), 2):
            if i + 1 < len(stops):
                stop_num = stops[i].strip()
                stop_content = stops[i+1].strip()
                
                # Extract the actual stop title from the content
                lines = stop_content.split('\n')
                if lines:
                    # Use the full content for text
                    text_content.append(stop_content)
    
    return {
        "tour_name": tour_name,
        "text_content": text_content,
        "audio_files": []  # Will be filled by TTS
    }

def convert_old_tour_to_modernized(tour_content, location, tour_type):
    """Convert old tour format to modernized structure"""
    # Parse the actual tour content from the working tour
    import re
    
    # Extract tour name from content
    tour_name_match = re.search(r'Step-by-Step Audio Guided Tour: (.+?)\n', tour_content)
    tour_name = tour_name_match.group(1) if tour_name_match else f"{location} - {tour_type} Tour"
    
    # Split content by stops
    stops = re.split(r'\n\s*Stop\s+(\d+):', tour_content)
    
    text_content = []
    audio_files = []
    
    if len(stops) > 1:
        stops = stops[1:]  # Remove title part
        
        # Process stops in pairs (number, content)
        for i in range(0, len(stops), 2):
            if i + 1 < len(stops):
                stop_num = stops[i].strip()
                stop_content = stops[i+1].strip()
                
                # Extract the actual stop title and content
                lines = stop_content.split('\n')
                if lines:
                    stop_title = lines[0].strip()
                    full_content = stop_content
                    
                    text_content.append(full_content)
                    # Create placeholder audio data (will be replaced by actual TTS)
                    audio_files.append(base64.b64encode(f"Audio content for {stop_title}".encode()).decode())
    
    return {
        "tour_name": tour_name,
        "text_content": text_content,
        "audio_files": audio_files
    }

def process_modernized_tour_async(job_id, tour_data):
    """Process tour with modernized structure"""
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = "Creating modernized tour structure..."
        
        zip_filename = create_modernized_tour_zip(tour_data, job_id)
        
        ACTIVE_JOBS[job_id]["status"] = "completed"
        ACTIVE_JOBS[job_id]["progress"] = "Modernized tour created successfully!"
        ACTIVE_JOBS[job_id]["output_zip"] = zip_filename
        ACTIVE_JOBS[job_id]["modernized"] = True
        
    except Exception as e:
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "tour_generation_modernized", "version": SERVICE_VERSION})

@app.route('/create-modernized-tour', methods=['POST'])
def create_modernized_tour():
    """Create tour with separate MP3/TXT files"""
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    job_id = str(uuid.uuid4())
    
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for processing",
        "created_at": datetime.now().isoformat(),
        "modernized": True
    }
    
    thread = threading.Thread(
        target=process_modernized_tour_async,
        args=(job_id, data)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"job_id": job_id, "status": "queued", "modernized": True})

@app.route('/process', methods=['POST'])
def process_tour():
    """Process existing tour file into modernized format"""
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    tour_file = data.get('tour_file')
    if not tour_file:
        return jsonify({"error": "tour_file parameter is required"}), 400
    
    # Check if tour file exists
    tour_file_path = os.path.join(TOURS_DIR, tour_file)
    if not os.path.exists(tour_file_path):
        return jsonify({"error": f"Tour file '{tour_file}' not found"}), 404
    
    job_id = str(uuid.uuid4())
    
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for modernized tour processing",
        "created_at": datetime.now().isoformat(),
        "tour_file": tour_file,
        "modernized": True
    }
    
    thread = threading.Thread(
        target=generate_modernized_tour_async,
        args=(job_id, tour_file_path)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"job_id": job_id, "status": "queued", "modernized": True})

@app.route('/download/<job_id>', methods=['GET'])
def download_tour(job_id):
    """Download the modernized tour ZIP"""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed"}), 400
    
    zip_path = os.path.join(TOURS_DIR, job["output_zip"])
    if not os.path.exists(zip_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(zip_path, as_attachment=True, download_name=job["output_zip"])

@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify(ACTIVE_JOBS[job_id])

if __name__ == '__main__':
    os.makedirs(TOURS_DIR, exist_ok=True)
    print(f"Starting Modernized Tour Generation Service v{SERVICE_VERSION}")
    app.run(host='0.0.0.0', port=5021, debug=False)