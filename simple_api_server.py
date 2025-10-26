"""
Simple API server for updating tour status.
"""
from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_db():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        database="audiotours",
        user="admin",
        password="password123"
    )

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})

@app.route('/update_tour', methods=['POST'])
def update_tour():
    """Update tour status directly."""
    try:
        data = request.json
        if not data or 'tour_id' not in data:
            return jsonify({'error': 'Missing tour_id'}), 400
        
        tour_id = data['tour_id']
        status = data.get('status', 'completed')
        timestamp = datetime.now().isoformat()
        
        logger.info(f"Updating tour {tour_id} to {status}")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Update the tour status
        sql = f"UPDATE tour_requests SET status = '{status}', finished_at = '{timestamp}' WHERE tour_id = '{tour_id}'"
        logger.info(f"Executing: {sql}")
        cur.execute(sql)
        
        conn.commit()
        rows = cur.rowcount
        
        # Verify the update
        cur.execute(f"SELECT id, tour_id, status, finished_at FROM tour_requests WHERE tour_id = '{tour_id}'")
        result = cur.fetchone()
        if result:
            logger.info(f"Updated tour: id={result[0]}, tour_id={result[1]}, status={result[2]}, finished_at={result[3]}")
        
        cur.close()
        conn.close()
        
        if rows > 0:
            return jsonify({'status': 'success', 'rows_affected': rows})
        else:
            return jsonify({'status': 'error', 'message': f'No tour found with ID {tour_id}'}), 404
    
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting API server on port 5003")
    app.run(host='0.0.0.0', port=5003)