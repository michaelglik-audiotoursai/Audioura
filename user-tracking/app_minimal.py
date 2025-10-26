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

@app.route('/users', methods=['GET'])
def list_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT secret_id FROM users ORDER BY created_at DESC')
    users = cur.fetchall()
    user_list = [user[0] for user in users]
    cur.close()
    conn.close()
    return jsonify({"users": user_list})

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)