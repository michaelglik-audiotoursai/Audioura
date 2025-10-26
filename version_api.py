#!/usr/bin/env python3
"""
Simple Version API for REQ-012
"""
import time
from datetime import datetime
from flask import Flask, jsonify

app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "version_api"})

@app.route('/tour/<int:tour_id>/version', methods=['GET'])
def get_tour_version(tour_id):
    """Get tour version for mobile app"""
    current_timestamp = int(time.time())
    version = f"1.2.5.{current_timestamp}"
    
    return jsonify({
        'tour_id': tour_id,
        'version': version,
        'last_modified': datetime.now().isoformat(),
        'has_updates': True,
        'download_url': f'/download-tour/{tour_id}?v={current_timestamp}'
    })

@app.route('/tours/check-versions', methods=['POST'])
def check_versions():
    """Bulk version check"""
    from flask import request
    data = request.json or []
    
    results = []
    for item in data:
        tour_id = item.get('tour_id')
        local_version = item.get('local_version', '1.0.0')
        
        if tour_id:
            server_version = f"1.2.5.{int(time.time())}"
            results.append({
                'tour_id': tour_id,
                'server_version': server_version,
                'local_version': local_version,
                'needs_update': server_version != local_version
            })
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5023, debug=False)