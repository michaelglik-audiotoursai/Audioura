"""
Modernized Tour Generation Service - Separate MP3/TXT Files
Implements REQ-001: Tour ZIP Structure Modernization
"""
SERVICE_VERSION = "1.2.5.184"

import os
import re
import json
import uuid
import zipfile
import base64
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading

# Labels stripped from TTS audio (kept in .txt files for mobile app parsing)
# Matches all 5 structured metadata fields — same set as translation_service._NAV_FIELD_PREFIXES
_NAV_LABEL_RE = re.compile(
    r'^\s*(Address|Coordinates|Type/Specialty|Specific Examples|Operational Details)\s*:',
    re.IGNORECASE | re.MULTILINE
)

def _strip_nav_fields_for_tts(text):
    """Remove structured metadata lines before sending to Polly.
    Keeps: stop name, Orientation, and all narrative paragraphs.
    Strips: Address, Coordinates, Type/Specialty, Specific Examples, Operational Details.
    The .txt files are written from the original text and remain unchanged."""
    lines = text.split('\n')
    return '\n'.join(l for l in lines if not _NAV_LABEL_RE.match(l))

from job_store import get_job_store

def _get_auth_token(target_url):
    """Get identity token for Cloud Run service-to-service auth."""
    if not target_url.startswith('https://'):
        return {}
    try:
        from urllib.parse import urlparse
        parsed = urlparse(target_url)
        audience = f"{parsed.scheme}://{parsed.netloc}"
        resp = requests.get(
            f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={audience}",
            headers={"Metadata-Flavor": "Google"}, timeout=5)
        if resp.status_code == 200:
            return {"Authorization": f"Bearer {resp.text}"}
    except:
        pass
    return {}

app = Flask(__name__)
CORS(app)

TOURS_DIR = "/app/tours"
ACTIVE_JOBS = get_job_store('tour-generation-modernized')

# Inter-service URLs
POLLY_TTS_URL = os.getenv('POLLY_TTS_URL', 'http://polly-tts-1:5018')

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

_COORDINATES_RE = re.compile(r'^Coordinates:\s*[-\d.]+\s*,\s*[-\d.]+', re.IGNORECASE | re.MULTILINE)
_CATEGORY_ICONS = {'walking': '🚶', 'restaurant': '🍴', 'museum': '🏛️', 'specialized': '🗺️'}

def _stop_has_coordinates(stop_text):
    """Return True if the stop text contains a Coordinates: line with valid lat,lng."""
    return bool(_COORDINATES_RE.search(stop_text))

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
        .map-btn {{ background: #3d7ebf; border: none; border-radius: 50%; width: 36px; height: 36px;
                    font-size: 20px; line-height: 1;
                    cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
                    margin-left: 8px; vertical-align: middle; }}
    </style>
</head>
<body>
    <h1>{tour_name.replace('_', ' ').title()}</h1>
    <script>
        function openMap(stopNum) {{
            if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {{
                window.flutter_inappwebview.callHandler('openMap', {{stop: stopNum}});
            }}
        }}
    </script>'''
    
    for i, text in enumerate(stops, 1):
        # Extract stop title from text content
        lines = text.split('\n')
        stop_title = lines[0].strip() if lines else f"Stop {i}"
        
        map_button = ''
        if _stop_has_coordinates(text):
            icon = _CATEGORY_ICONS.get(tour_data.get('tour_category', ''), '🗺️')
            map_button = f'<button class="map-btn" onclick="openMap({i})" title="View on map">{icon}</button>'
        
        html += f'''
    <div class="audio-item">
        <h3>{stop_title}: Audio {i}</h3>
        {map_button}
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
                    audioElements.forEach((otherAudio, otherIndex) => {
                        if (otherIndex !== index && !otherAudio.paused) {
                            otherAudio.pause();
                        }
                    });
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

def generate_modernized_tour_async(job_id, tour_file_path, user_id=None, orchestrator_job_id=None):
    """Generate modernized tour from existing tour text file"""
    try:
        ACTIVE_JOBS.update(job_id, status="processing", progress="Processing tour text file...")
        
        # Read the tour text file
        with open(tour_file_path, 'r', encoding='utf-8') as f:
            tour_content = f.read()
        
        # Parse the tour content using the same logic as the working system
        ACTIVE_JOBS.update(job_id, progress="Parsing tour content...")
        modernized_data = parse_tour_content_to_modernized(tour_content)

        # [BETA-4 / wdvrdaxqjn] Validate stop coordinates before anything consumes
        # them. Coordinates arrive here as a "Coordinates:" line the language model
        # wrote from memory, and nothing had ever checked them — measured errors of
        # 1-2 km, and one stop that put a Toronto car park on an island reachable
        # only by ferry. This runs before the zip is built, so both audio_N.txt
        # (which the map reads) and the map buttons in the HTML get the corrected
        # values. Fail-soft: any geocoder problem leaves the original untouched.
        ACTIVE_JOBS.update(job_id, progress="Validating stop coordinates...")
        try:
            import geocode_stops
            hint = geocode_stops.location_hint(modernized_data.get("tour_name", ""))
            anchor = geocode_stops.geocode(hint) if hint else None
            modernized_data["text_content"], geo_records = geocode_stops.correct_stops(
                modernized_data["text_content"], hint, tour_anchor=anchor)
            corrected = sum(1 for r in geo_records if r.get("action") == "replaced")
            if corrected:
                print(f"[GEOCODE] corrected {corrected} of {len(geo_records)} stop coordinates")
        except Exception as e:
            print(f"[GEOCODE] validation skipped ({e}); keeping model coordinates")

        # Generate audio using TTS service
        ACTIVE_JOBS.update(job_id, progress="Generating audio files...")
        audio_files = []
        for i, text_content in enumerate(modernized_data["text_content"], 1):
            try:
                # Call Polly TTS service (with auth for Cloud Run)
                tts_headers = {"Content-Type": "application/json"}
                tts_headers.update(_get_auth_token(POLLY_TTS_URL))
                # [LOCAL-323] Forward user_id and job_id for cost attribution
                tts_payload = {
                    "text": _strip_nav_fields_for_tts(text_content),
                    "voice": "Joanna",
                }
                if user_id:
                    tts_payload["user_id"] = user_id
                if orchestrator_job_id:
                    tts_payload["job_id"] = orchestrator_job_id
                tts_response = requests.post(
                    f"{POLLY_TTS_URL}/synthesize",
                    headers=tts_headers,
                    json=tts_payload,
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
        ACTIVE_JOBS.update(job_id, progress="Creating modernized tour ZIP...")
        zip_filename = create_modernized_tour_zip(modernized_data, job_id)
        
        ACTIVE_JOBS.update(job_id, status="completed",
                          progress="Modernized tour created successfully!",
                          output_zip=zip_filename, modernized=True)
        
    except Exception as e:
        ACTIVE_JOBS.update(job_id, status="error", error=str(e))

def parse_tour_content_to_modernized(tour_content):
    """Parse tour text content into modernized structure"""
    import re
    
    # Extract tour name from content
    tour_name_match = re.search(r'Step-by-Step Audio Guided Tour: (.+?)\n', tour_content)
    tour_name = tour_name_match.group(1) if tour_name_match else "Audio Tour"

    # Extract tour category written by generate_tour_text.py (e.g. "Tour-Category: walking").
    # Anchored to start-of-string and limited to first 200 chars so a stop description
    # containing "Tour-Category:" mid-file can never produce a false positive.
    category_match = re.search(r'^Tour-Category:\s*(\w+)', tour_content[:500], re.IGNORECASE | re.MULTILINE)
    tour_category = category_match.group(1).lower() if category_match else ''

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
        "tour_category": tour_category,
        "text_content": text_content,
        "audio_files": []  # Will be filled by TTS
    }


def process_modernized_tour_async(job_id, tour_data):
    """Process tour with modernized structure"""
    try:
        ACTIVE_JOBS.update(job_id, status="processing", progress="Creating modernized tour structure...")
        
        zip_filename = create_modernized_tour_zip(tour_data, job_id)
        
        ACTIVE_JOBS.update(job_id, status="completed",
                          progress="Modernized tour created successfully!",
                          output_zip=zip_filename, modernized=True)
        
    except Exception as e:
        ACTIVE_JOBS.update(job_id, status="error", error=str(e))

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
    """Process existing tour file into modernized format.
    
    Accepts EITHER:
      - tour_file: filename to read from /app/tours/ (local Docker mode)
      - tour_content: inline text content (Cloud Run mode, no shared volume)
    Optional attribution fields (LOCAL-323):
      - user_id: user who triggered the tour (forwarded to TTS metering)
      - job_id: orchestrator job_id (forwarded to TTS metering)
    """
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    tour_file = data.get('tour_file')
    tour_content = data.get('tour_content')
    # [LOCAL-323] Accept user_id and job_id for cost attribution
    user_id = data.get('user_id')
    orchestrator_job_id = data.get('job_id')
    
    if not tour_file and not tour_content:
        return jsonify({"error": "Either 'tour_file' or 'tour_content' parameter is required"}), 400
    
    # Determine the source of tour text
    tour_file_path = None
    if tour_content:
        # Cloud mode: write content to /tmp/ for processing
        import tempfile
        tmp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir='/tmp')
        tmp_file.write(tour_content)
        tmp_file.close()
        tour_file_path = tmp_file.name
        print(f"Cloud mode: wrote tour_content ({len(tour_content)} chars) to {tour_file_path}")
    elif tour_file:
        # Volume mode: read from shared volume
        tour_file_path = os.path.join(TOURS_DIR, tour_file)
        if not os.path.exists(tour_file_path):
            return jsonify({"error": f"Tour file '{tour_file}' not found"}), 404
    
    job_id = str(uuid.uuid4())
    
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for modernized tour processing",
        "created_at": datetime.now().isoformat(),
        "tour_file": tour_file or "inline_content",
        "modernized": True
    }
    
    thread = threading.Thread(
        target=generate_modernized_tour_async,
        args=(job_id, tour_file_path, user_id, orchestrator_job_id)
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
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5021')), debug=False)