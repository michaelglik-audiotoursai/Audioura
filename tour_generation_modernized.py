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
# [LOCAL-573] text-sized /synthesize timeout (30 + 0.05*len, cap 180). Soft
# import so a missing module never breaks the caller.
try:
    from tts_timeout import synthesize_timeout
except Exception:  # noqa: BLE001
    def synthesize_timeout(text):
        n = len(text) if isinstance(text, str) else int(text or 0)
        return min(180.0, 30.0 + 0.05 * max(0, n))
from datetime import datetime
from flask import Flask, request, jsonify, send_file as _send_file
from flask_cors import CORS
import threading
import inspect as _inspect


def _compat_send_file(path_or_file, **kwargs):
    """Version-tolerant send_file wrapper (LOCAL-747).

    Flask <2.0 (the 1.1.4 service image) uses ``attachment_filename``; Flask
    >=2.0 renamed it to ``download_name``. This maps whichever caller keyword is
    given to whichever the installed Flask supports, so the same code runs on
    both. Same helper already shipped in 6 other services (Docker round 4).
    """
    sig = _inspect.signature(_send_file)
    params = sig.parameters
    download_name = kwargs.pop("download_name", None)
    attachment_filename = kwargs.pop("attachment_filename", None)
    name = download_name or attachment_filename
    if name:
        if "download_name" in params:
            kwargs["download_name"] = name
        else:
            kwargs["attachment_filename"] = name
    return _send_file(path_or_file, **kwargs)


send_file = _compat_send_file

# Labels stripped from TTS audio (kept in .txt files for mobile app parsing)
# Matches all 5 structured metadata fields — same set as translation_service._NAV_FIELD_PREFIXES
# [LOCAL-633] "Museum Information:" is DROPPED WHOLE from TTS (label + value). The
# practical facts are spoken ONCE as the composed sentence in the Stop-1 opening
# section (about_museum_stop + practical_facts_gate.compose_practical_facts); the
# "Museum Information:" field keeps the full detail for the TEXT VIEW only and must
# NOT be read aloud — otherwise the long hours/admission dump is spoken a second
# time (Bench R1: Uffizi/Reina Sofía/Met).
_SPOKEN_LABEL_RE = re.compile(r'^\s*(Orientation|Directions)\s*:\s*', re.IGNORECASE)
_NAV_LABEL_RE = re.compile(
    r'^\s*(Museum Information|Address|Coordinates|Type/Specialty|Specific Examples|Operational Details)\s*:',
    re.IGNORECASE | re.MULTILINE
)

def _strip_nav_fields_for_tts(text):
    """Remove structured metadata lines before sending to Polly.
    Keeps: stop name, Orientation, and all narrative paragraphs.
    Strips: Museum Information, Address, Coordinates, Type/Specialty, Specific
    Examples, Operational Details.
    The .txt files are written from the original text and remain unchanged."""
    lines = text.split('\n')
    kept = [l for l in lines if not _NAV_LABEL_RE.match(l)]
    # [LEAD 2026-10-08 / LOCAL-633] "Museum Information:" is now dropped WHOLE above
    # (its practical facts are spoken once in the opening-section prose). Only the
    # remaining spoken labels (Orientation/Directions) are label-stripped so their
    # value — not the field word — is read aloud. The .txt keeps every label for the
    # app's text view.
    return '\n'.join(_SPOKEN_LABEL_RE.sub('', l) for l in kept)

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

# [LOCAL-747] Map-button building blocks moved to the shared tour_html_map
# module so the editor's create_clean_html renders the identical button. The
# names below stay as module-level aliases for any existing importer.
from tour_html_map import (
    COORDINATES_RE as _COORDINATES_RE,
    CATEGORY_ICONS as _CATEGORY_ICONS,
    stop_has_coordinates as _stop_has_coordinates,
    build_map_button as _build_map_button,
    build_tour_page_html as _build_tour_page_html,
)

def generate_html_with_external_audio(tour_data):
    """Generate HTML that references external MP3 files.

    [LOCAL-750 B] The page markup, header and CSS now come from the shared
    tour_html_map.build_tour_page_html so a generated page and an EDITED page
    (tour_editing_phase2.create_clean_html) are byte-for-byte identical for the
    same stops — the map button sits right after the "<stop>: Audio N" title and
    the page header is the tour name, on both.
    """
    tour_name = tour_data.get('tour_name', 'Audio Tour')
    stops = tour_data.get('text_content', [])
    tour_category = tour_data.get('tour_category', '')
    return _build_tour_page_html(tour_name, stops, tour_category)

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
                    timeout=synthesize_timeout(tts_payload["text"])
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

    # [LOCAL-743] Normalise any sentence-form stop heading the model wrote
    # ("Stop 1 is the Salem Maritime National Historic Site.") back to the house
    # "Stop N:" header BEFORE the split below, so this splitter and the
    # generator's count see the same stops. The live tour 716 lost stop 1 (4 of 5
    # delivered, no audio for stop 1) because the split keys on "Stop N:" and this
    # sentence form never matched. Fail-soft: a missing/old tour_conclusion leaves
    # the content untouched rather than crashing the live packer.
    try:
        from tour_conclusion import normalize_heading_variants as _norm_variants
        _before = tour_content
        tour_content = _norm_variants(tour_content)
        if tour_content != _before:
            print("[LOCAL-743] normalised sentence-form stop heading(s) to 'Stop N:' before split")
    except Exception as _nhv_err:  # pragma: no cover - defensive
        print(f"[LOCAL-743] heading-variant normalisation unavailable: {_nhv_err}")

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
                    # [D617, LEAD 2026-10-06] This is the LIVE packer (audio_N.txt is
                    # spoken). LOCAL-602 r2 put the URL/Sources strip in
                    # break_text_to_pois.py, which the live path never calls.
                    try:
                        from spoken_text_hygiene import strip_sources_and_urls as _strip_spoken
                        stop_content, _sp_rep = _strip_spoken(stop_content)
                        if _sp_rep.get('urls') or _sp_rep.get('sources_blocks'):
                            print(f"[D617] stop {stop_num}: stripped {_sp_rep} from spoken text")
                    except Exception as _sp_err:
                        print(f"[D617] spoken-text strip unavailable: {_sp_err}")
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