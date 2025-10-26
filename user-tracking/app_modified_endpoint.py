from flask import Flask, request, jsonify
import psycopg2
import json
from datetime import datetime
import os
import traceback

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

@app.route('/user', methods=['POST'])
def add_user():
    data = request.json
    secret_id = data.get('secret_id')
    coordinates = data.get('coordinates', {})
    app_version = data.get('app_version', 'unknown')
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO users (secret_id, app_version) 
        VALUES (%s, %s) 
        ON CONFLICT (secret_id) DO NOTHING
    ''', (secret_id, app_version))
    
    if coordinates:
        cur.execute('''
            INSERT INTO coordinates (secret_id, lat, lng) 
            VALUES (%s, %s, %s)
        ''', (secret_id, coordinates.get('lat'), coordinates.get('lng')))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/user/<secret_id>', methods=['PUT'])
def update_user(secret_id):
    data = request.json
    print(f"Updating user: {secret_id}, data: {data}")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Ensure user exists before adding related data
    cur.execute('''
        INSERT INTO users (secret_id, app_version) 
        VALUES (%s, %s) 
        ON CONFLICT (secret_id) DO NOTHING
    ''', (secret_id, data.get('app_version', 'unknown')))
    
    if 'coordinates' in data:
        cur.execute('''
            INSERT INTO coordinates (secret_id, lat, lng) 
            VALUES (%s, %s, %s)
        ''', (secret_id, data['coordinates'].get('lat'), data['coordinates'].get('lng')))
    
    if 'tour_request' in data:
        cur.execute('''
            INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at) 
            VALUES (%s, %s, %s, %s, %s)
        ''', (secret_id, data['tour_request'].get('tour_id'), data['tour_request'].get('request_string'), 'started', datetime.now()))
    
    if 'tour_status_update' in data:
        tour_id = data['tour_status_update'].get('tour_id')
        status = data['tour_status_update'].get('status')
        finished_at = data['tour_status_update'].get('finished_at', datetime.now().isoformat())
        
        print(f"Updating tour status: tour_id={tour_id}, status={status}, finished_at={finished_at}")
        
        # First check if the tour exists and belongs to this user
        cur.execute('''
            SELECT id FROM tour_requests 
            WHERE secret_id = %s AND tour_id = %s
        ''', (secret_id, tour_id))
        
        tour = cur.fetchone()
        if tour:
            print(f"Tour found: {tour[0]}, proceeding with update")
            cur.execute('''
                UPDATE tour_requests 
                SET status = %s, finished_at = %s 
                WHERE secret_id = %s AND tour_id = %s
            ''', (status, finished_at, secret_id, tour_id))
            
            # Verify the update
            cur.execute('''
                SELECT id, status, finished_at FROM tour_requests 
                WHERE secret_id = %s AND tour_id = %s
            ''', (secret_id, tour_id))
            
            updated_tour = cur.fetchone()
            if updated_tour:
                print(f"Tour updated: id={updated_tour[0]}, status={updated_tour[1]}, finished_at={updated_tour[2]}")
            else:
                print(f"Tour update verification failed")
        else:
            print(f"Tour not found for user {secret_id}, tour_id={tour_id}")
    
    if 'map_request' in data:
        coords = data['map_request'].get('coordinates', {})
        cur.execute('''
            INSERT INTO map_requests (secret_id, lat, lng) 
            VALUES (%s, %s, %s)
        ''', (secret_id, coords.get('lat'), coords.get('lng')))
    
    if 'app_uninstalled' in data:
        cur.execute('''
            UPDATE users SET app_uninstalled = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE secret_id = %s
        ''', (data['app_uninstalled'], secret_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/user/<secret_id>', methods=['DELETE'])
def delete_user(secret_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET is_deleted = TRUE, updated_at = CURRENT_TIMESTAMP 
        WHERE secret_id = %s
    ''', (secret_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/user/<secret_id>', methods=['GET'])
def get_user(secret_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM users WHERE secret_id = %s', (secret_id,))
    user = cur.fetchone()
    
    if not user:
        cur.close()
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    cur.execute('SELECT id, lat, lng, created_at FROM coordinates WHERE secret_id = %s ORDER BY created_at', (secret_id,))
    coordinates = cur.fetchall()
    
    cur.execute('SELECT id, tour_id, request_string, status, created_at FROM tour_requests WHERE secret_id = %s ORDER BY created_at', (secret_id,))
    tours = cur.fetchall()
    
    cur.execute('SELECT id, lat, lng, created_at FROM map_requests WHERE secret_id = %s ORDER BY created_at', (secret_id,))
    maps = cur.fetchall()
    
    user_data = {
        'secret_id': user[0],
        'app_version': user[1],
        'is_deleted': user[2],
        'app_uninstalled': user[3],
        'created_at': user[4].isoformat() if user[4] else None,
        'updated_at': user[5].isoformat() if user[5] else None,
        'total_records': len(coordinates) + len(tours) + len(maps),
        'coordinates': [{
            'id': c[0],
            'lat': c[1],
            'lng': c[2],
            'timestamp': c[3].isoformat() if c[3] else None
        } for c in coordinates],
        'tours': [{
            'id': t[0],
            'tour_id': t[1],
            'request_string': t[2],
            'status': t[3],
            'timestamp': t[4].isoformat() if t[4] else None
        } for t in tours],
        'map_requests': [{
            'id': m[0],
            'lat': m[1],
            'lng': m[2],
            'timestamp': m[3].isoformat() if m[3] else None
        } for m in maps]
    }
    
    cur.close()
    conn.close()
    return jsonify(user_data)

# Add a special endpoint that uses the existing user endpoint
@app.route('/tour/<tour_id>/update', methods=['POST'])
def update_tour_via_user(tour_id):
    """Update tour status by finding the user and using the user endpoint."""
    try:
        data = request.json
        status = data.get('status', 'completed')
        
        print(f"Updating tour {tour_id} to status {status}")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Find the user who owns this tour
        cur.execute("SELECT secret_id FROM tour_requests WHERE tour_id = %s", (tour_id,))
        result = cur.fetchone()
        
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': f'No tour found with ID {tour_id}'}), 404
        
        secret_id = result[0]
        print(f"Found tour owned by user {secret_id}")
        
        # Update the tour using the existing user endpoint logic
        finished_at = datetime.now().isoformat()
        
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
                'user_id': secret_id,
                'rows_affected': rows_affected
            })
        else:
            return jsonify({'error': f'Failed to update tour with ID {tour_id}'}), 500
    
    except Exception as e:
        print(f"Error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask app...")
    print("Routes defined:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")
    app.run(host='0.0.0.0', port=5000, debug=True)