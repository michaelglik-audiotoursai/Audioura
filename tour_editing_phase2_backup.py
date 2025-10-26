"""
Phase 2 Tour Editing Backend - REQ-003 Implementation
Provides endpoints for tour text editing with audio regeneration
"""
SERVICE_VERSION = "1.2.6.189"

import os
import json
import uuid
import zipfile
import shutil
import requests
import psycopg2
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)

TOURS_DIR = "/app/tours"
ACTIVE_JOBS = {}
POLLY_TTS_URL = "http://polly-tts-1:5018"

def get_db_connection():
    """Get database connection for distribution sync"""
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def sync_to_distribution_service(tour_path, tour_id):
    """Sync updated tour to distribution service database"""
    try:
        # Create new ZIP from updated tour directory
        zip_path = tour_path.parent / f"{tour_path.name}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in tour_path.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(tour_path)
                    zipf.write(file_path, arcname)
        
        # Read ZIP data
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
        # Update distribution database
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Find tour by ID or UUID prefix
        if tour_id.isdigit():
            # Direct ID match
            cur.execute("""
                UPDATE audio_tours 
                SET audio_tour = %s
                WHERE id = %s
            """, (zip_data, int(tour_id)))
        else:
            # Extract UUID from directory name (e.g., american_wing_in_mfa_boston_ma__museum_272f3f80)
            uuid_part = tour_id.split('_')[-1] if '_' in tour_id else tour_id
            
            # Try multiple matching strategies
            cur.execute("""
                SELECT id FROM audio_tours 
                WHERE tour_name ILIKE %s OR request_string ILIKE %s OR tour_name ILIKE %s
                LIMIT 1
            """, (f'%american%wing%mfa%', f'%american%wing%', f'%{uuid_part}%'))
            
            result = cur.fetchone()
            if result:
                tour_db_id = result[0]
                print(f"Found matching tour ID {tour_db_id} for directory {tour_id}")
                cur.execute("""
                    UPDATE audio_tours 
                    SET audio_tour = %s
                    WHERE id = %s
                """, (zip_data, tour_db_id))
            else:
                print(f"No matching tour found for {tour_id}")
                return False
        
        rows_updated = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"Distribution sync: Updated {rows_updated} tours in database")
        return rows_updated > 0
        
    except Exception as e:
        print(f"Distribution sync error: {e}")
        return False

def resolve_numeric_to_uuid_directory(tour_id):
    """Map numeric tour ID to UUID directory - ISSUE-001 fix"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tour_name FROM audio_tours WHERE id = %s", (int(tour_id),))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            tour_name = result[0].lower()
            tours_dir = Path(TOURS_DIR)
            
            # Find matching UUID directory by tour name keywords
            keywords = ['harvard', 'university', 'campus', 'cambridge'] if 'harvard' in tour_name else []
            if 'american' in tour_name and 'wing' in tour_name:
                keywords = ['american', 'wing', 'mfa']
            
            for item in tours_dir.iterdir():
                if item.is_dir():
                    item_name_lower = item.name.lower()
                    if keywords and all(keyword in item_name_lower for keyword in keywords[:2]):
                        return item
                        
        return None
    except Exception as e:
        print(f"Error resolving numeric tour {tour_id}: {e}")
        return None

def resolve_tour_to_directory(tour_identifier):
    """Resolve both numeric and UUID tour identifiers to directory path"""
    tours_dir = Path(TOURS_DIR)
    
    # Try exact match first
    exact_path = tours_dir / tour_identifier
    if exact_path.exists():
        return exact_path
    
    # Handle numeric tour IDs (like 49) - ISSUE-001 fix
    if tour_identifier.isdigit():
        return resolve_numeric_to_uuid_directory(tour_identifier)
    
    # Handle UUID formats
    uuid_part = None
    if '-' in tour_identifier:
        # Full UUID format: b2561a69-feff-409d-806b-f7a09efbb745
        uuid_part = tour_identifier.split('-')[0]
    elif len(tour_identifier) >= 8:
        # UUID prefix: b2561a69
        uuid_part = tour_identifier[:8]
    
    if uuid_part:
        # Find directory containing UUID prefix
        for item in tours_dir.iterdir():
            if item.is_dir() and uuid_part in item.name:
                return item
    
    return None

def get_tour_edit_info(tour_id):
    """Extract tour information for editing - supports both database and UUID tours"""
    # Use enhanced resolver for both numeric and UUID tours
    tour_path = resolve_tour_to_directory(tour_id)
    
    if not tour_path:
        return None
    
    stops = []
    text_files = sorted(tour_path.glob("audio_*.txt"))
    
    for i, text_file in enumerate(text_files, 1):
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read().strip()
            
            stops.append({
                "stop_number": i,
                "text_content": text_content,
                "audio_file": f"audio_{i}.mp3",
                "editable": True
            })
        except Exception as e:
            print(f"Error reading {text_file}: {e}")
    
    return {
        "tour_id": tour_id,
        "tour_name": tour_id.replace('_', ' ').title(),
        "stops": stops
    }

def regenerate_audio_async(job_id, tour_id, stop_number, text_content, voice="Joanna"):
    """Generate new audio using Polly TTS service"""
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = 50
        
        # Call Polly TTS service
        tts_response = requests.post(f"{POLLY_TTS_URL}/synthesize", json={
            "text": text_content,
            "voice": voice,
            "format": "mp3"
        }, timeout=30)
        
        if tts_response.status_code == 200:
            audio_data = tts_response.content
            
            # Save new audio file
            tour_path = Path(TOURS_DIR) / tour_id
            audio_file = tour_path / f"audio_{stop_number}.mp3"
            
            with open(audio_file, 'wb') as f:
                f.write(audio_data)
            
            # Update ZIP file
            update_tour_zip(tour_id)
            
            ACTIVE_JOBS[job_id]["status"] = "completed"
            ACTIVE_JOBS[job_id]["progress"] = 100
            ACTIVE_JOBS[job_id]["audio_ready"] = True
            ACTIVE_JOBS[job_id]["audio_url"] = f"/tours/{tour_id}/audio_{stop_number}.mp3"
            
        else:
            raise Exception(f"TTS service error: {tts_response.status_code}")
            
    except Exception as e:
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)

def update_tour_zip(tour_id):
    """Rebuild tour ZIP with updated files"""
    tour_path = Path(TOURS_DIR) / tour_id
    zip_path = Path(TOURS_DIR) / f"{tour_id}.zip"
    
    if zip_path.exists():
        # Backup original
        backup_path = Path(TOURS_DIR) / f"{tour_id}_backup.zip"
        shutil.copy2(zip_path, backup_path)
    
    # Create new ZIP
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in tour_path.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(tour_path)
                zipf.write(file_path, arcname)

def update_html_with_cache_busting(tour_path, updated_stops, cache_version):
    """Update HTML with cache-busting parameters for updated audio files"""
    html_file = tour_path / "index.html"
    if not html_file.exists():
        return
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Add cache-busting parameters to updated audio files
    for stop_num in updated_stops:
        old_src = f'src="audio_{stop_num}.mp3"'
        new_src = f'src="audio_{stop_num}.mp3?v={cache_version}"'
        html_content = html_content.replace(old_src, new_src)
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

def create_backup(tour_path):
    """Create backup of tour directory before bulk changes"""
    backup_path = tour_path.parent / f"{tour_path.name}_backup"
    if backup_path.exists():
        shutil.rmtree(backup_path)
    shutil.copytree(tour_path, backup_path)
    return backup_path

def restore_backup(tour_path, backup_path):
    """Restore tour directory from backup"""
    if tour_path.exists():
        shutil.rmtree(tour_path)
    shutil.copytree(backup_path, tour_path)
    shutil.rmtree(backup_path)

def create_new_tour_with_changes(original_tour_path, changes_made=False, updated_stops=None):
    """Create new tour directory with changes for UUID tours - REQ-016
    Only copies unchanged audio files, avoids unnecessary TTS generation"""
    if not changes_made:
        # No changes made, return original tour info
        return {
            'new_tour_created': False,
            'new_tour_id': None,
            'tour_path': original_tour_path
        }
    
    # Generate new UUID for the updated tour
    new_uuid = str(uuid.uuid4())
    new_uuid_prefix = new_uuid.split('-')[0]
    
    # Create new directory name based on original but with new UUID prefix
    original_name = original_tour_path.name
    if '_' in original_name:
        # Replace UUID part in directory name
        name_parts = original_name.split('_')
        name_parts[-1] = new_uuid_prefix  # Replace last part (UUID) with new UUID prefix
        new_dir_name = '_'.join(name_parts)
    else:
        new_dir_name = f"{original_name}_{new_uuid_prefix}"
    
    new_tour_path = original_tour_path.parent / new_dir_name
    
    # Create new directory
    new_tour_path.mkdir(exist_ok=True)
    
    # Copy all files, but skip audio files for changed stops (they will be regenerated)
    updated_stops_set = set(updated_stops or [])
    
    for file_path in original_tour_path.rglob('*'):
        if file_path.is_file():
            relative_path = file_path.relative_to(original_tour_path)
            
            # Check if this is an audio file for a changed stop
            if file_path.name.startswith('audio_') and file_path.suffix == '.mp3':
                try:
                    stop_number = int(file_path.stem.split('_')[1])
                    if stop_number in updated_stops_set:
                        # Skip copying audio for changed stops - will be regenerated
                        continue
                except (ValueError, IndexError):
                    pass  # Copy file if we can't parse stop number
            
            # Copy unchanged files (including text files, HTML, and unchanged audio)
            dest_path = new_tour_path / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_path)
    
    return {
        'new_tour_created': True,
        'new_tour_id': new_uuid,
        'tour_path': new_tour_path,
        'directory_name': new_dir_name
    }

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "tour_editing_phase2", "version": SERVICE_VERSION})

@app.route('/tour/<tour_id>/version', methods=['GET'])
def get_tour_version(tour_id):
    """Get tour version for mobile app - REQ-012"""
    import time
    current_timestamp = int(time.time())
    version = f"1.2.5.{current_timestamp}"
    
    return jsonify({
        'tour_id': tour_id,
        'version': version,
        'last_modified': datetime.now().isoformat(),
        'has_updates': True,
        'download_url': f'http://localhost:5005/download-tour/{tour_id}?v={current_timestamp}'
    })

@app.route('/tours/check-versions', methods=['POST'])
def check_multiple_versions():
    """Bulk version check for mobile app - REQ-012"""
    data = request.json or []
    results = []
    
    for item in data:
        tour_id = item.get('tour_id')
        local_version = item.get('local_version', '1.0.0')
        
        if tour_id:
            import time
            server_version = f"1.2.5.{int(time.time())}"
            results.append({
                'tour_id': tour_id,
                'server_version': server_version,
                'local_version': local_version,
                'needs_update': server_version != local_version
            })
    
    return jsonify(results)

@app.route('/tour/<tour_id>/edit-info', methods=['GET'])
def get_edit_info(tour_id):
    """Get tour metadata for editing"""
    tour_info = get_tour_edit_info(tour_id)
    if not tour_info:
        return jsonify({"error": "Tour not found"}), 404
    return jsonify(tour_info)

@app.route('/tour/<tour_id>/update-stop', methods=['POST'])
def update_stop(tour_id):
    """Update text content for a specific stop"""
    data = request.json
    stop_number = data.get('stop_number')
    new_text = data.get('new_text')
    
    if not stop_number or not new_text:
        return jsonify({"error": "stop_number and new_text required"}), 400
    
    # Find tour directory using enhanced resolver (numeric + UUID)
    tour_path = resolve_tour_to_directory(tour_id)
    
    if not tour_path:
        tours_dir = Path(TOURS_DIR)
        available_tours = [d.name for d in tours_dir.iterdir() if d.is_dir()]
        return jsonify({
            "error": "Tour not found",
            "details": f"Tour directory '{tour_id}' does not exist",
            "expected_format": "Numeric ID (49) or UUID (full or prefix)",
            "available_tours": available_tours[:10],
            "numeric_lookup_attempted": tour_id.isdigit()
        }), 404
    
    # Update text file
    text_file = tour_path / f"audio_{stop_number}.txt"
    try:
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(new_text)
        
        # Start audio generation job
        job_id = str(uuid.uuid4())
        ACTIVE_JOBS[job_id] = {
            "status": "queued",
            "progress": 0,
            "tour_id": tour_id,
            "stop_number": stop_number,
            "created_at": datetime.now().isoformat()
        }
        
        thread = threading.Thread(
            target=regenerate_audio_async,
            args=(job_id, str(tour_path.name), stop_number, new_text)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "success",
            "job_id": job_id,
            "message": "Audio generation started"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tour/<tour_id>/update-multiple-stops', methods=['POST'])
def update_multiple_stops(tour_id):
    """Atomic bulk update of multiple stops with versioning and cache-busting"""
    data = request.json
    stops = data.get('stops', [])
    
    if not stops:
        return jsonify({"error": "stops array is required"}), 400
    
    # Find tour directory using enhanced UUID resolution
    tour_path = Path(TOURS_DIR) / tour_id
    if not tour_path.exists():
        tour_path = resolve_tour_to_directory(tour_id)
        
        if not tour_path:
            return jsonify({"error": "Tour not found", "uuid_lookup_attempted": True}), 404
    
    # Create backup before making changes
    backup_path = None
    try:
        backup_path = create_backup(tour_path)
        
        # CRITICAL FIX: Read ALL existing stops from original tour first
        print(f"PRESERVE: Reading original stops from {tour_path}")
        original_stops = {}
        text_files = sorted(tour_path.glob("audio_*.txt"))
        
        for text_file in text_files:
            try:
                stop_num = int(text_file.stem.split('_')[1])
                with open(text_file, 'r', encoding='utf-8') as f:
                    text_content = f.read().strip()
                original_stops[stop_num] = {
                    'stop_number': stop_num,
                    'text_content': text_content,
                    'action': 'preserve',
                    'has_custom_audio': True,
                    'audio_source': 'preserved'
                }
                print(f"PRESERVE: Found original stop {stop_num}")
            except (ValueError, IndexError) as e:
                print(f"PRESERVE: Error parsing {text_file}: {e}")
        
        print(f"PRESERVE: Total original stops: {len(original_stops)} - {list(original_stops.keys())}")
        
        # Process changes and collect updated stops
        updated_stops = []
        skipped_stops = []
        job_ids = []
        cache_version = str(int(datetime.now().timestamp()))
        
        # Phase 1: Process incoming changes and merge with original stops
        for stop_data in stops:
            stop_number = stop_data.get('stop_number')
            new_text = stop_data.get('new_text')
            original_text = stop_data.get('original_text')
            action = stop_data.get('action', 'modify')
            
            if not stop_number or not new_text:
                continue
            
            print(f"PRESERVE: Processing stop {stop_number} with action={action}")
            
            # Update or add stop to original_stops collection
            if action == 'add' or new_text != original_text:
                updated_stops.append(stop_number)
                
                # Update the stop in our collection
                original_stops[stop_number] = {
                    'stop_number': stop_number,
                    'text_content': new_text,
                    'action': action,
                    'has_custom_audio': stop_data.get('has_custom_audio', False),
                    'audio_source': 'user_recorded' if stop_data.get('has_custom_audio') else 'tts',
                    'custom_audio_data': stop_data.get('custom_audio_data')
                }
                
                # Start audio generation job
                job_id = str(uuid.uuid4())
                ACTIVE_JOBS[job_id] = {
                    "status": "queued",
                    "progress": 0,
                    "tour_id": str(tour_path.name),
                    "stop_number": stop_number,
                    "created_at": datetime.now().isoformat(),
                    "bulk_job": True,
                    "cache_version": cache_version,
                    "deferred_generation": True
                }
                
                job_ids.append(job_id)
            else:
                skipped_stops.append(stop_number)
        
        # Create final stops data from preserved + updated stops
        final_stops_data = list(original_stops.values())
        print(f"PRESERVE: Final stops before renumbering: {[s['stop_number'] for s in final_stops_data]}")
        
        # CRITICAL FIX: Renumber stops sequentially to eliminate gaps
        print(f"RENUMBER: Before - stops: {[s['stop_number'] for s in final_stops_data]}")
        for i, stop_data in enumerate(final_stops_data):
            old_number = stop_data['stop_number']
            new_number = i + 1
            stop_data['stop_number'] = new_number
            if old_number != new_number:
                print(f"RENUMBER: Stop {old_number} -> {new_number}")
        
        print(f"RENUMBER: After - stops: {[s['stop_number'] for s in final_stops_data]}")
        
        # Phase 2: Create new tour with changes for UUID tours (REQ-016)
        changes_made = len(updated_stops) > 0
        new_tour_info = create_new_tour_with_changes(tour_path, changes_made, updated_stops)
        
        final_tour_path = new_tour_info['tour_path']
        
        # Phase 2.5: Write ALL stops (preserved + updated) to new tour directory
        print(f"PRESERVE: Writing {len(final_stops_data)} stops to new tour {final_tour_path}")
        for stop_data in final_stops_data:
            stop_number = stop_data['stop_number']
            text_content = stop_data['text_content']
            
            # Write text file
            text_file = final_tour_path / f"audio_{stop_number}.txt"
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            # Copy audio file if it's preserved (not updated)
            if stop_data['action'] == 'preserve':
                # Find original audio file (before renumbering)
                for orig_num in original_stops.keys():
                    if original_stops[orig_num] == stop_data:
                        original_audio = tour_path / f"audio_{orig_num}.mp3"
                        new_audio = final_tour_path / f"audio_{stop_number}.mp3"
                        if original_audio.exists():
                            shutil.copy2(original_audio, new_audio)
                            print(f"PRESERVE: Copied audio {orig_num} -> {stop_number}")
                        break
            
            # Handle custom audio for updated stops
            elif stop_data.get('has_custom_audio') and stop_data.get('custom_audio_data'):
                try:
                    import base64
                    audio_data = base64.b64decode(stop_data['custom_audio_data'])
                    audio_file = final_tour_path / f"audio_{stop_number}.mp3"
                    with open(audio_file, 'wb') as f:
                        f.write(audio_data)
                    print(f"PRESERVE: Saved custom audio for stop {stop_number}")
                except Exception as e:
                    print(f"PRESERVE: Error saving custom audio for stop {stop_number}: {e}")
        
        # Phase 3: Generate audio for changed stops in new tour directory
        if job_ids:
            # Start audio generation threads for new tour
            for job_id in job_ids:
                if job_id in ACTIVE_JOBS:
                    job = ACTIVE_JOBS[job_id]
                    stop_number = job["stop_number"]
                    
                    # Find the new text for this stop
                    new_text = None
                    for stop_data in stops:
                        if stop_data.get('stop_number') == stop_number:
                            new_text = stop_data.get('new_text')
                            break
                    
                    if new_text:
                        thread = threading.Thread(
                            target=regenerate_audio_async,
                            args=(job_id, str(final_tour_path.name), stop_number, new_text)
                        )
                        thread.daemon = True
                        thread.start()
            
            # Wait for all jobs to complete (with timeout)
            max_wait = 60  # 60 seconds timeout
            wait_count = 0
            
            while wait_count < max_wait:
                completed_jobs = 0
                failed_jobs = 0
                
                for job_id in job_ids:
                    if job_id in ACTIVE_JOBS:
                        status = ACTIVE_JOBS[job_id]["status"]
                        if status == "completed":
                            completed_jobs += 1
                        elif status == "error":
                            failed_jobs += 1
                
                if completed_jobs == len(job_ids):
                    break
                elif failed_jobs > 0:
                    # Rollback on any failure
                    restore_backup(tour_path, backup_path)
                    return jsonify({
                        "status": "error",
                        "message": "Audio generation failed, changes rolled back",
                        "failed_jobs": failed_jobs
                    }), 500
                
                time.sleep(1)
                wait_count += 1
            
            if wait_count >= max_wait:
                # Timeout - rollback changes
                restore_backup(tour_path, backup_path)
                return jsonify({
                    "status": "error",
                    "message": "Audio generation timeout, changes rolled back"
                }), 500
        
        # Phase 3: Update HTML with cache-busting parameters
        if updated_stops:
            update_html_with_cache_busting(tour_path, updated_stops, cache_version)
        
        # final_tour_path already set in Phase 2
        
        # Phase 4: Rebuild ZIP file
        update_tour_zip(str(final_tour_path.name))
        
        # Phase 5: Sync to distribution service
        distribution_synced = sync_to_distribution_service(final_tour_path, tour_id)
        
        # Clean up backup on success
        if backup_path and backup_path.exists():
            shutil.rmtree(backup_path)
        
        # Generate tour version
        tour_version = f"1.2.6.{cache_version[-3:]}"
        
        # Prepare response with new tour ID (REQ-016)
        response = {
            "status": "success",
            "message": f"Bulk update completed: {len(updated_stops)} stops updated, {len(skipped_stops)} skipped",
            "updated_stops": updated_stops,
            "skipped_stops": skipped_stops,
            "tour_version": tour_version,
            "cache_version": cache_version,
            "job_ids": job_ids,
            "distribution_updated": distribution_synced
        }
        
        # Add new tour ID if new tour was created (REQ-016)
        if new_tour_info['new_tour_created']:
            response["new_tour_id"] = new_tour_info['new_tour_id']
            response["download_url"] = f"/tour/{new_tour_info['new_tour_id']}/download"
            response["stops"] = [{"stop_number": s["stop_number"], "audio_source": s["audio_source"]} for s in final_stops_data]
        else:
            response["new_tour_id"] = tour_id
            response["download_url"] = f"/tour/{tour_id}/download"
            response["stops"] = [{"stop_number": s["stop_number"], "audio_source": s["audio_source"]} for s in final_stops_data]
        
        return jsonify(response)
        
    except Exception as e:
        # Rollback on any error
        if backup_path and backup_path.exists():
            try:
                restore_backup(tour_path, backup_path)
            except:
                pass
        
        return jsonify({
            "status": "error",
            "message": f"Bulk update failed: {str(e)}",
            "rollback": "completed"
        }), 500

@app.route('/tour/<tour_id>/regenerate-audio', methods=['POST'])
def regenerate_audio(tour_id):
    """Generate new MP3 from text using Polly TTS"""
    data = request.json
    stop_number = data.get('stop_number')
    text_content = data.get('text_content')
    voice = data.get('voice', 'Joanna')
    
    if not stop_number or not text_content:
        return jsonify({"error": "stop_number and text_content required"}), 400
    
    job_id = str(uuid.uuid4())
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": 0,
        "tour_id": tour_id,
        "stop_number": stop_number,
        "created_at": datetime.now().isoformat()
    }
    
    thread = threading.Thread(
        target=regenerate_audio_async,
        args=(job_id, tour_id, stop_number, text_content, voice)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "success",
        "job_id": job_id,
        "message": "Audio generation started"
    })

@app.route('/tour/<tour_id>/job-status/<job_id>', methods=['GET'])
def get_job_status(tour_id, job_id):
    """Check audio generation progress"""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "audio_ready": job.get("audio_ready", False)
    }
    
    if job["status"] == "completed":
        response["audio_url"] = job.get("audio_url")
    elif job["status"] == "error":
        response["error"] = job.get("error")
    
    return jsonify(response)

@app.route('/tour/<tour_id>/add-stop', methods=['POST'])
def add_stop(tour_id):
    """Add new stop to tour with automatic renumbering"""
    data = request.json
    position = data.get('position')
    title = data.get('title', 'New Stop')
    text_content = data.get('text', '')
    insert_mode = data.get('insert_mode', 'append')
    
    if not text_content or len(text_content) < 10:
        return jsonify({"error": "Text content required (minimum 10 characters)"}), 400
    
    # Find tour directory using enhanced UUID resolution
    tour_path = Path(TOURS_DIR) / tour_id
    if not tour_path.exists():
        tour_path = resolve_uuid_to_directory(tour_id)
        
        if not tour_path:
            return jsonify({"error": "Tour not found", "uuid_lookup_attempted": True}), 404
    
    try:
        backup_path = create_backup(tour_path)
        current_stops = sorted([int(f.stem.split('_')[1]) for f in tour_path.glob("audio_*.txt")])
        max_stops = len(current_stops)
        
        if max_stops >= 20:
            restore_backup(tour_path, backup_path)
            return jsonify({"error": "Maximum 20 stops per tour"}), 400
        
        new_position = max_stops + 1 if insert_mode == 'append' else min(max(1, position), max_stops + 1)
        
        # Renumber existing files
        renumbered_stops = []
        for stop_num in reversed(current_stops):
            if stop_num >= new_position:
                old_audio = tour_path / f"audio_{stop_num}.mp3"
                old_text = tour_path / f"audio_{stop_num}.txt"
                new_audio = tour_path / f"audio_{stop_num + 1}.mp3"
                new_text = tour_path / f"audio_{stop_num + 1}.txt"
                
                if old_audio.exists():
                    shutil.move(str(old_audio), str(new_audio))
                if old_text.exists():
                    shutil.move(str(old_text), str(new_text))
                
                renumbered_stops.append(stop_num + 1)
        
        # Create new stop files
        new_text_file = tour_path / f"audio_{new_position}.txt"
        with open(new_text_file, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        # Generate audio
        tts_response = requests.post(f"{POLLY_TTS_URL}/synthesize", json={
            "text": text_content,
            "voice": "Joanna",
            "format": "mp3"
        }, timeout=30)
        
        if tts_response.status_code == 200:
            new_audio_file = tour_path / f"audio_{new_position}.mp3"
            with open(new_audio_file, 'wb') as f:
                f.write(tts_response.content)
        else:
            restore_backup(tour_path, backup_path)
            return jsonify({"error": "Audio generation failed"}), 500
        
        cache_version = str(int(datetime.now().timestamp()))
        
        # Rebuild HTML with proper sequential naming for voice control
        rebuild_html_with_sequential_naming(tour_path, max_stops + 1, cache_version)
        
        update_tour_zip(str(tour_path.name))
        sync_to_distribution_service(tour_path, tour_id)
        
        if backup_path.exists():
            shutil.rmtree(backup_path)
        
        return jsonify({
            "status": "success",
            "message": f"Stop added at position {new_position}",
            "new_stop_number": new_position,
            "renumbered_stops": sorted(renumbered_stops, reverse=True),
            "tour_version": f"1.2.6.{cache_version[-3:]}",
            "cache_version": cache_version
        })
        
    except Exception as e:
        if backup_path and backup_path.exists():
            restore_backup(tour_path, backup_path)
        return jsonify({"error": f"Add stop failed: {str(e)}"}), 500

@app.route('/tour/<tour_id>/delete-stop', methods=['POST'])
def delete_stop(tour_id):
    """Delete stop from tour with automatic renumbering"""
    data = request.json
    stop_number = data.get('stop_number')
    
    if not stop_number:
        return jsonify({"error": "stop_number required"}), 400
    
    # Find tour directory using enhanced UUID resolution
    tour_path = Path(TOURS_DIR) / tour_id
    if not tour_path.exists():
        tour_path = resolve_uuid_to_directory(tour_id)
        
        if not tour_path:
            return jsonify({"error": "Tour not found", "uuid_lookup_attempted": True}), 404
    
    try:
        backup_path = create_backup(tour_path)
        current_stops = sorted([int(f.stem.split('_')[1]) for f in tour_path.glob("audio_*.txt")])
        
        if len(current_stops) <= 2:
            restore_backup(tour_path, backup_path)
            return jsonify({"error": "Cannot delete - minimum 2 stops required"}), 400
        
        if stop_number not in current_stops:
            restore_backup(tour_path, backup_path)
            return jsonify({"error": f"Stop {stop_number} does not exist"}), 404
        
        # Delete stop files
        audio_file = tour_path / f"audio_{stop_number}.mp3"
        text_file = tour_path / f"audio_{stop_number}.txt"
        
        if audio_file.exists():
            audio_file.unlink()
        if text_file.exists():
            text_file.unlink()
        
        # Renumber remaining files
        renumbered_stops = []
        for stop_num in current_stops:
            if stop_num > stop_number:
                old_audio = tour_path / f"audio_{stop_num}.mp3"
                old_text = tour_path / f"audio_{stop_num}.txt"
                new_audio = tour_path / f"audio_{stop_num - 1}.mp3"
                new_text = tour_path / f"audio_{stop_num - 1}.txt"
                
                if old_audio.exists():
                    shutil.move(str(old_audio), str(new_audio))
                if old_text.exists():
                    shutil.move(str(old_text), str(new_text))
                
                renumbered_stops.append(stop_num - 1)
        
        cache_version = str(int(datetime.now().timestamp()))
        
        # Rebuild HTML with proper sequential naming for voice control
        rebuild_html_with_sequential_naming(tour_path, len(current_stops) - 1, cache_version)
        
        update_tour_zip(str(tour_path.name))
        sync_to_distribution_service(tour_path, tour_id)
        
        if backup_path.exists():
            shutil.rmtree(backup_path)
        
        return jsonify({
            "status": "success",
            "message": f"Stop {stop_number} deleted, remaining stops renumbered",
            "deleted_stop": stop_number,
            "renumbered_stops": renumbered_stops,
            "tour_version": f"1.2.6.{cache_version[-3:]}",
            "cache_version": cache_version
        })
        
    except Exception as e:
        if backup_path and backup_path.exists():
            restore_backup(tour_path, backup_path)
        return jsonify({"error": f"Delete stop failed: {str(e)}"}), 500

def rebuild_html_with_sequential_naming(tour_path, total_stops, cache_version):
    """Rebuild HTML with proper sequential naming for voice control compatibility"""
    html_file = tour_path / "index.html"
    if not html_file.exists():
        return
    
    # Read all text files to get content
    stops_data = []
    for i in range(1, total_stops + 1):
        text_file = tour_path / f"audio_{i}.txt"
        if text_file.exists():
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read().strip()
            # Extract title from first line or use default
            title = text_content.split('\n')[0][:50] + f": Audio {i}"
            stops_data.append({
                'number': i,
                'title': title,
                'text': text_content
            })
    
    # Generate new HTML with sequential naming
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tour</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .audio-item {{ margin: 20px 0; padding: 15px; border: 1px solid #ccc; }}
        audio {{ width: 100%; }}
    </style>
</head>
<body>
    <h1>Audio Tour</h1>
'''
    
    # Add audio elements with proper sequential naming
    for stop in stops_data:
        i = stop['number']
        html_content += f'''    <div class="audio-item">
        <h3>{stop['title']}</h3>
        <audio id="audio-{i-1}" controls preload="metadata">
            <source src="audio_{i}.mp3?v={cache_version}" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
    </div>
'''
    
    # Add voice control JavaScript
    html_content += '''
    <script>
        let audioElements = [];
        let currentStopIndex = 0;
        
        window.playAudio = function() {
            audioElements.forEach((audio, index) => {
                if (index !== currentStopIndex) {
                    audio.pause();
                    audio.currentTime = 0;
                }
            });
            
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
        
        document.addEventListener('DOMContentLoaded', function() {
            const audios = document.querySelectorAll('audio');
            audioElements = Array.from(audios);
            
            audioElements.forEach((audio, index) => {
                audio.addEventListener('play', function() {
                    currentStopIndex = index;
                });
            });
        });
    </script>
</body>
</html>'''
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

@app.route('/tour/<tour_id>/download', methods=['GET'])
def download_tour(tour_id):
    """Download UUID tour as ZIP file - REQ-016"""
    from flask import send_file
    
    # Find tour directory using UUID resolution
    tour_path = Path(TOURS_DIR) / tour_id
    if not tour_path.exists():
        tour_path = resolve_uuid_to_directory(tour_id)
        
        if not tour_path:
            return jsonify({"error": "Tour not found", "uuid_lookup_attempted": True}), 404
    
    # Check if ZIP file exists
    zip_path = Path(TOURS_DIR) / f"{tour_path.name}.zip"
    if not zip_path.exists():
        # Create ZIP file if it doesn't exist
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in tour_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(tour_path)
                        zipf.write(file_path, arcname)
        except Exception as e:
            return jsonify({"error": f"Failed to create ZIP: {str(e)}"}), 500
    
    try:
        return send_file(str(zip_path), as_attachment=True, download_name=f"{tour_path.name}.zip")
    except Exception as e:
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

if __name__ == '__main__':
    os.makedirs(TOURS_DIR, exist_ok=True)
    print(f"Starting Phase 2 Tour Editing Service v{SERVICE_VERSION}")
    print(f"Polly TTS URL: {POLLY_TTS_URL}")
    app.run(host='0.0.0.0', port=5022, debug=False)" r e s o l v e _ u u i d _ t o _ d i r e c t o r y   =   r e s o l v e _ t o u r _ t o _ d i r e c t o r y "    
 