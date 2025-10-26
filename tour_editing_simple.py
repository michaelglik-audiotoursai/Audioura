#!/usr/bin/env python3
import json
import os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import uuid
import shutil
import zipfile

SERVICE_VERSION = "1.2.2.105"
TOURS_DIR = "tours"

class TourEditingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')
        
        if len(path_parts) >= 3 and path_parts[0] == 'tour' and path_parts[2] == 'edit-info':
            tour_id = path_parts[1]
            self.handle_get_tour_edit_info(tour_id)
        elif len(path_parts) >= 2 and path_parts[0] == 'tours-near':
            self.handle_get_tours_near()
        else:
            self.send_error(404)
    
    def do_POST(self):
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')
        
        if len(path_parts) >= 3 and path_parts[0] == 'tour':
            tour_id = path_parts[1]
            action = path_parts[2]
            
            if action == 'update-stop':
                self.handle_update_stop(tour_id)
            elif action == 'create-custom':
                self.handle_create_custom(tour_id)
            else:
                self.send_error(404)
        else:
            self.send_error(404)
    
    def handle_get_tour_edit_info(self, tour_id):
        tour_data = self.get_tour_structure(tour_id)
        if not tour_data:
            self.send_json_response({"error": "Tour not found"}, 404)
            return
        self.send_json_response(tour_data)
    
    def handle_get_tours_near(self):
        tours = []
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
                        parts = tour_id.split('_')
                        if len(parts) >= 3:
                            tour_info["original_tour_id"] = '_'.join(parts[1:-1])
                    
                    tours.append(tour_info)
        
        self.send_json_response({"tours": tours})
    
    def handle_update_stop(self, tour_id):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        stop_number = data.get('stop_number')
        new_text = data.get('new_text')
        
        tour_path = Path(TOURS_DIR) / tour_id
        if not tour_path.exists():
            self.send_json_response({"error": "Tour not found"}, 404)
            return
        
        # Save text modification
        text_file = tour_path / f"stop_{stop_number}_text.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(new_text)
        
        self.send_json_response({"status": "success", "message": "Stop updated"})
    
    def handle_create_custom(self, tour_id):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        custom_name = data.get('custom_name')
        modifications = data.get('modifications', [])
        
        custom_tour_id = f"custom_{tour_id}_{str(uuid.uuid4())[:8]}"
        
        original_path = Path(TOURS_DIR) / tour_id
        custom_path = Path(TOURS_DIR) / custom_tour_id
        
        if not original_path.exists():
            self.send_json_response({"error": "Original tour not found"}, 404)
            return
        
        try:
            shutil.copytree(original_path, custom_path)
            
            for mod in modifications:
                stop_num = mod.get('stop_number')
                new_text = mod.get('new_text')
                
                if new_text:
                    text_file = custom_path / f"stop_{stop_num}_text.txt"
                    with open(text_file, 'w', encoding='utf-8') as f:
                        f.write(new_text)
            
            self.send_json_response({
                "custom_tour_id": custom_tour_id,
                "download_url": f"/download-tour/{custom_tour_id}",
                "status": "completed"
            })
            
        except Exception as e:
            self.send_json_response({"error": f"Custom tour creation failed: {str(e)}"}, 500)
    
    def get_tour_structure(self, tour_id):
        tour_path = Path(TOURS_DIR) / tour_id
        if not tour_path.exists():
            return None
        
        tour_name = tour_id.replace('_', ' ').title()
        stops = []
        audio_files = list(tour_path.glob("*.mp3"))
        
        for i, audio_file in enumerate(sorted(audio_files), 1):
            stops.append({
                "stop_number": i,
                "title": f"Stop {i}",
                "current_text": f"Audio content for stop {i}",
                "audio_file": audio_file.name,
                "audio_duration": 45,
                "editable": True
            })
        
        return {
            "tour_id": tour_id,
            "tour_name": tour_name,
            "stops": stops
        }
    
    def send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 5020), TourEditingHandler)
    print(f"Tour Editing Service v{SERVICE_VERSION} running on port 5020")
    server.serve_forever()