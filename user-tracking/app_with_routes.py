from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime
import os
from routes import register_routes

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

# Register additional routes
register_routes(app, get_db)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)