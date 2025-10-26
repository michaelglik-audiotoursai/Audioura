"""
Script to create a simple Flask API for updating tour status.
"""
from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime
import os

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

@app.route('/users', methods=['GET'])
def get_users():
    """Return a list of users."""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT secret_id, created_at FROM users ORDER BY created_at DESC LIMIT 10')
        users = cur.fetchall()
        
        user_list = []
        for user in users:
            user_list.append({
                'secret_id': user[0],
                'created_at': user[1].isoformat() if user[1] else None
            })
        
        cur.close()
        conn.close()
        
        return jsonify({
            'total_users': len(user_list),
            'users': user_list
        })
    except Exception as e:
        print(f"Error getting users: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/update_tour', methods=['POST'])
def update_tour():
    """Update tour status directly."""
    try:
        data = request.json
        if not data or 'tour_id' not in data or 'status' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        tour_id = data['tour_id']
        status = data['status']
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
        cur.close()
        conn.close()
        
        if rows_affected == 0:
            return jsonify({'error': f'No tour found with ID {tour_id}'}), 404
        
        return jsonify({
            'status': 'success',
            'tour_id': tour_id,
            'rows_affected': rows_affected
        })
    
    except Exception as e:
        print(f"Update Tour Error: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/sql', methods=['POST'])
def execute_sql():
    """Execute SQL directly on the database."""
    try:
        data = request.json
        if not data or 'sql' not in data:
            return jsonify({'error': 'No SQL provided'}), 400
        
        sql = data['sql']
        print(f"Executing SQL: {sql}")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Execute the SQL
        cur.execute(sql)
        
        # If it's a SELECT query, return the results
        if sql.strip().upper().startswith('SELECT'):
            columns = [desc[0] for desc in cur.description]
            results = []
            for row in cur.fetchall():
                results.append(dict(zip(columns, row)))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify(results)
        
        # For other queries, commit and return success
        conn.commit()
        rows_affected = cur.rowcount
        cur.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'rows_affected': rows_affected
        })
    
    except Exception as e:
        print(f"SQL Error: {e}")
        return jsonify({
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    app.run(host='0.0.0.0', port=port, debug=True)