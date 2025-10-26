from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime
import os

app = Flask(__name__)

def get_db():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})

@app.route('/update', methods=['POST'])
def update_tour():
    """Update tour status directly."""
    try:
        data = request.json
        if not data or 'tour_id' not in data:
            return jsonify({'error': 'Missing tour_id'}), 400
        
        tour_id = data['tour_id']
        status = data.get('status', 'completed')
        finished_at = data.get('finished_at', datetime.now().isoformat())
        
        print(f"Updating tour {tour_id} to status {status}")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Update the tour status
        cur.execute(
            "UPDATE tour_requests SET status = %s, finished_at = %s WHERE tour_id = %s",
            (status, finished_at, tour_id)
        )
        
        conn.commit()
        rows_affected = cur.rowcount
        
        # Verify the update
        cur.execute("SELECT id, status, finished_at FROM tour_requests WHERE tour_id = %s", (tour_id,))
        updated_tour = cur.fetchone()
        if updated_tour:
            print(f"Tour updated: id={updated_tour[0]}, status={updated_tour[1]}, finished_at={updated_tour[2]}")
        
        cur.close()
        conn.close()
        
        if rows_affected > 0:
            return jsonify({
                'status': 'success',
                'tour_id': tour_id,
                'rows_affected': rows_affected
            })
        else:
            return jsonify({'error': f'No tour found with ID {tour_id}'}), 404
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Tour Update Service...")
    print("Routes defined:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")
    app.run(host='0.0.0.0', port=5001, debug=True)