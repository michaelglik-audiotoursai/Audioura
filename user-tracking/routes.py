from flask import request, jsonify
from datetime import datetime

def register_routes(app, get_db):
    @app.route('/update_tour', methods=['POST'])
    def update_tour():
        data = request.json
        if not data or 'tour_id' not in data:
            return jsonify({'error': 'Missing tour_id'}), 400
        
        tour_id = data['tour_id']
        status = data.get('status', 'completed')
        
        conn = get_db()
        cur = conn.cursor()
        
        # Direct SQL update
        cur.execute(
            "UPDATE tour_requests SET status = %s, finished_at = %s WHERE tour_id = %s",
            (status, datetime.now(), tour_id)
        )
        
        conn.commit()
        rows = cur.rowcount
        cur.close()
        conn.close()
        
        if rows > 0:
            return jsonify({'status': 'success', 'rows_affected': rows})
        else:
            return jsonify({'status': 'error', 'message': f'No tour found with ID {tour_id}'}), 404