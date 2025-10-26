from flask import Flask, request, jsonify
import psycopg2
import json
from datetime import datetime
import os
import traceback
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_db():
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        logger.info("Database connection successful")
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            secret_id VARCHAR(255) PRIMARY KEY,
            app_version VARCHAR(50),
            is_deleted BOOLEAN DEFAULT FALSE,
            app_uninstalled BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS coordinates (
            id SERIAL PRIMARY KEY,
            secret_id VARCHAR(255) REFERENCES users(secret_id),
            lat FLOAT,
            lng FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tour_requests (
            id SERIAL PRIMARY KEY,
            secret_id VARCHAR(255) REFERENCES users(secret_id),
            tour_id VARCHAR(255),
            request_string TEXT,
            status VARCHAR(50) DEFAULT 'started',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS map_requests (
            id SERIAL PRIMARY KEY,
            secret_id VARCHAR(255) REFERENCES users(secret_id),
            lat FLOAT,
            lng FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Database initialized successfully")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})

@app.route('/user', methods=['POST'])
def add_user():
    data = request.json
    secret_id = data.get('secret_id')
    coordinates = data.get('coordinates', {})
    app_version = data.get('app_version', 'unknown')
    
    logger.info(f"Adding user: {secret_id}, app_version: {app_version}")
    
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
    logger.info(f"Updating user: {secret_id}, data: {data}")
    
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
        
        logger.info(f"Updating tour status: tour_id={tour_id}, status={status}, finished_at={finished_at}")
        
        # First check if the tour exists and belongs to this user
        cur.execute('''
            SELECT id FROM tour_requests 
            WHERE secret_id = %s AND tour_id = %s
        ''', (secret_id, tour_id))
        
        tour = cur.fetchone()
        if tour:
            logger.info(f"Tour found: {tour[0]}, proceeding with update")
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
                logger.info(f"Tour updated: id={updated_tour[0]}, status={updated_tour[1]}, finished_at={updated_tour[2]}")
            else:
                logger.warning(f"Tour update verification failed")
        else:
            logger.warning(f"Tour not found for user {secret_id}, tour_id={tour_id}")
    
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
    logger.info(f"Deleting user: {secret_id}")
    
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

@app.route('/users', methods=['GET'])
def list_all_users():
    logger.info("Listing all users")
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT secret_id, app_version, is_deleted, app_uninstalled, created_at, updated_at FROM users ORDER BY created_at DESC')
    users = cur.fetchall()
    
    user_list = []
    for user in users:
        # Get counts for each user
        cur.execute('SELECT COUNT(*) FROM coordinates WHERE secret_id = %s', (user[0],))
        coord_count = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM tour_requests WHERE secret_id = %s', (user[0],))
        tour_count = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM map_requests WHERE secret_id = %s', (user[0],))
        map_count = cur.fetchone()[0]
        
        user_list.append({
            'secret_id': user[0],
            'app_version': user[1],
            'is_deleted': user[2],
            'app_uninstalled': user[3],
            'created_at': user[4].isoformat() if user[4] else None,
            'updated_at': user[5].isoformat() if user[5] else None,
            'total_records': coord_count + tour_count + map_count,
            'coordinates_count': coord_count,
            'tours_count': tour_count,
            'map_requests_count': map_count
        })
    
    cur.close()
    conn.close()
    
    return jsonify({
        'total_users': len(user_list),
        'users': user_list
    })

@app.route('/user/<secret_id>', methods=['GET'])
def get_user(secret_id):
    logger.info(f"Getting user: {secret_id}")
    
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

@app.route('/update_tour', methods=['POST'])
def update_tour():
    """Update tour status directly."""
    try:
        data = request.json
        if not data or 'tour_id' not in data:
            return jsonify({'error': 'Missing tour_id'}), 400
        
        tour_id = data['tour_id']
        status = data.get('status', 'completed')
        finished_at = data.get('finished_at', datetime.now().isoformat())
        
        logger.info(f"Updating tour {tour_id} to status {status}")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Update the tour status
        sql = f"UPDATE tour_requests SET status = '{status}', finished_at = '{finished_at}' WHERE tour_id = '{tour_id}'"
        logger.info(f"Executing SQL: {sql}")
        cur.execute(sql)
        
        conn.commit()
        rows_affected = cur.rowcount
        
        # Verify the update
        cur.execute(f"SELECT id, tour_id, status, finished_at FROM tour_requests WHERE tour_id = '{tour_id}'")
        result = cur.fetchone()
        if result:
            logger.info(f"Updated tour: id={result[0]}, tour_id={result[1]}, status={result[2]}, finished_at={result[3]}")
        
        cur.close()
        conn.close()
        
        if rows_affected > 0:
            return jsonify({'status': 'success', 'rows_affected': rows_affected})
        else:
            return jsonify({'status': 'error', 'message': f'No tour found with ID {tour_id}'}), 404
    
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    init_db()
    logger.info("Starting API server on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=True)