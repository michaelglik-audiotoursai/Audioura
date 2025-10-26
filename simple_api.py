"""
Simple API for updating tour status.
"""
from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime

app = Flask(__name__)

def get_db():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        database="audiotours",
        user="admin",
        password="password123"
    )

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
        
        print(f"Updating tour {tour_id} to {status}")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Update the tour status
        sql = f"UPDATE tour_requests SET status = '{status}', finished_at = '{timestamp}' WHERE tour_id = '{tour_id}'"
        print(f"Executing: {sql}")
        cur.execute(sql)
        
        conn.commit()
        rows = cur.rowcount
        cur.close()
        conn.close()
        
        if rows > 0:
            return jsonify({'status': 'success', 'rows_affected': rows})
        else:
            return jsonify({'status': 'error', 'message': f'No tour found with ID {tour_id}'}), 404
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/sql', methods=['POST'])
def execute_sql():
    """Execute SQL directly."""
    try:
        data = request.json
        if not data or 'sql' not in data:
            return jsonify({'error': 'Missing SQL'}), 400
        
        sql = data['sql']
        print(f"Executing: {sql}")
        
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute(sql)
        
        if sql.strip().upper().startswith('SELECT'):
            results = []
            for row in cur.fetchall():
                results.append(row)
            
            conn.commit()
            cur.close()
            conn.close()
            return jsonify(results)
        
        conn.commit()
        rows = cur.rowcount
        cur.close()
        conn.close()
        
        return jsonify({'status': 'success', 'rows_affected': rows})
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)