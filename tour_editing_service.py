from flask import Flask, request, jsonify
import os
import json
import zipfile
import base64
import shutil
from pathlib import Path
import uuid

app = Flask(__name__)
SERVICE_VERSION = "1.2.2.105"
TOURS_DIR = "tours"

def get_tour_structure(tour_id):
    """Extract tour structure from physical files"""
    tour_path = Path(TOURS_DIR) / tour_id
    if not tour_path.exists():
        return None
    
    # Read index.html to extract stops
    index_file = tour_path / "index.html"
    if not index_file.exists():
        return None
    
    with open(index_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract tour name from title
    tour_name = tour_id.replace('_', ' ').title()
    
    # Find audio files and extract stop info
    stops = []
    audio_files = list(tour_path.glob("*.mp3"))
    
    for i, audio_file in enumerate(sorted(audio_files), 1):
        stops.append({
            "stop_number": i,
            "title": f"Stop {i}",
            "current_text": f"Audio content for stop {i}",
            "audio_file": audio_file.name,
            "audio_duration": 45,  # Default duration
            "editable": True
        })
    
    return {
        "tour_id": tour_id,
        "tour_name": tour_name,
        "stops": stops
    }

@app.route('/tour/<tour_id>/edit-info', methods=['GET'])
def get_tour_edit_info(tour_id):
    """Get tour structure for editing"""
    tour_data = get_tour_structure(tour_id)
    if not tour_data:
        return jsonify({"error": "Tour not found"}), 404
    return jsonify(tour_data)

@app.route('/tour/<tour_id>/update-stop', methods=['POST'])
def update_tour_stop(tour_id):
    """Update individual stop content"""
    data = request.json
    stop_number = data.get('stop_number')
    new_text = data.get('new_text')
    audio_data = data.get('audio_file')
    
    tour_path = Path(TOURS_DIR) / tour_id
    if not tour_path.exists():
        return jsonify({"error": "Tour not found"}), 404
    
    # Save new audio if provided
    if audio_data:
        audio_filename = f"stop_{stop_number}.mp3"
        audio_path = tour_path / audio_filename
        
        # Decode base64 audio
        try:
            audio_bytes = base64.b64decode(audio_data)
            with open(audio_path, 'wb') as f:
                f.write(audio_bytes)
        except Exception as e:
            return jsonify({"error": f"Audio save failed: {str(e)}"}), 400
    
    # Update text in a simple text file
    text_file = tour_path / f"stop_{stop_number}_text.txt"
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(new_text)
    
    return jsonify({"status": "success", "message": "Stop updated"})

@app.route('/tour/<tour_id>/create-custom', methods=['POST'])
def create_custom_tour(tour_id):
    """Generate custom tour with modifications"""
    data = request.json
    custom_name = data.get('custom_name')
    modifications = data.get('modifications', [])
    
    # Generate custom tour ID
    custom_tour_id = f"custom_{tour_id}_{str(uuid.uuid4())[:8]}"
    
    # Copy original tour directory
    original_path = Path(TOURS_DIR) / tour_id
    custom_path = Path(TOURS_DIR) / custom_tour_id
    
    if not original_path.exists():
        return jsonify({"error": "Original tour not found"}), 404
    
    try:
        shutil.copytree(original_path, custom_path)
        
        # Apply modifications
        for mod in modifications:
            stop_num = mod.get('stop_number')
            new_text = mod.get('new_text')
            
            if new_text:
                text_file = custom_path / f"stop_{stop_num}_text.txt"
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(new_text)
        
        # Create zip file
        zip_path = Path(TOURS_DIR) / f"{custom_tour_id}.zip"
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file_path in custom_path.rglob('*'):
                if file_path.is_file():
                    zipf.write(file_path, file_path.relative_to(custom_path))
        
        return jsonify({
            "custom_tour_id": custom_tour_id,
            "download_url": f"/download-tour/{custom_tour_id}",
            "status": "completed"
        })
        
    except Exception as e:
        return jsonify({"error": f"Custom tour creation failed: {str(e)}"}), 500

@app.route('/tours-near/<lat>/<lng>', methods=['GET'])
def get_tours_near_enhanced(lat, lng):
    """Enhanced tours endpoint with custom tour support"""
    tours = []
    
    # Scan tours directory
    tours_path = Path(TOURS_DIR)
    if tours_path.exists():
        for tour_dir in tours_path.iterdir():
            if tour_dir.is_dir():
                tour_id = tour_dir.name
                is_custom = tour_id.startswith('custom_')
                
                tour_info = {
                    "id": tour_id,
                    "name": tour_id.replace('_', ' ').title(),
                    "is_custom": is_custom,
                    "original_tour_id": None
                }
                
                if is_custom:
                    # Extract original tour ID from custom tour ID
                    parts = tour_id.split('_')
                    if len(parts) >= 3:
                        tour_info["original_tour_id"] = '_'.join(parts[1:-1])
                
                tours.append(tour_info)
    
    return jsonify({"tours": tours})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5020, debug=True)