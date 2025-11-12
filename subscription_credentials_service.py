#!/usr/bin/env python3
"""
Subscription Credentials Service - Stage 1
Handles encrypted credential submission and storage
"""

import os
import psycopg2
from flask import Flask, request, jsonify
import logging
import json
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "subscription_credentials"})

@app.route('/submit_credentials', methods=['POST'])
def submit_credentials():
    """
    Submit encrypted credentials for subscription-required articles
    Stage 1: Store credentials securely for future processing
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['article_id', 'encrypted_username', 'encrypted_password', 'device_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    "status": "error",
                    "message": f"Missing required field: {field}"
                }), 400
        
        article_id = data['article_id']
        encrypted_username = data['encrypted_username']
        encrypted_password = data['encrypted_password']
        device_id = data['device_id']
        
        logging.info(f"Receiving credentials for article {article_id} from device {device_id}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify article exists and requires subscription
        cursor.execute("""
            SELECT subscription_required, subscription_domain, request_string 
            FROM article_requests 
            WHERE article_id = %s
        """, (article_id,))
        
        article_info = cursor.fetchone()
        if not article_info:
            cursor.close()
            conn.close()
            return jsonify({
                "status": "error",
                "message": "Article not found"
            }), 404
        
        subscription_required, subscription_domain, article_title = article_info
        
        if not subscription_required:
            cursor.close()
            conn.close()
            return jsonify({
                "status": "error",
                "message": "Article does not require subscription"
            }), 400
        
        if not subscription_domain:
            cursor.close()
            conn.close()
            return jsonify({
                "status": "error",
                "message": "Subscription domain not specified for article"
            }), 400
        
        # Verify device has encryption key
        cursor.execute("SELECT encryption_key FROM device_encryption_keys WHERE device_id = %s", (device_id,))
        device_key = cursor.fetchone()
        
        if not device_key:
            cursor.close()
            conn.close()
            return jsonify({
                "status": "error",
                "message": "Device encryption key not found. Please process a newsletter first."
            }), 400
        
        # Store encrypted credentials (replace existing if any)
        cursor.execute("""
            INSERT INTO user_subscription_credentials 
            (device_id, article_id, domain, encrypted_username, encrypted_password)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (device_id, article_id) 
            DO UPDATE SET 
                encrypted_username = EXCLUDED.encrypted_username,
                encrypted_password = EXCLUDED.encrypted_password,
                created_at = NOW()
        """, (device_id, article_id, subscription_domain, encrypted_username, encrypted_password))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logging.info(f"Credentials stored successfully for article {article_id}, domain {subscription_domain}")
        
        return jsonify({
            "status": "success",
            "message": f"Credentials submitted successfully for {subscription_domain}",
            "article_id": article_id,
            "article_title": article_title,
            "subscription_domain": subscription_domain
        })
        
    except Exception as e:
        logging.error(f"Error submitting credentials: {e}")
        return jsonify({
            "status": "error",
            "message": f"Failed to submit credentials: {str(e)}"
        }), 500

@app.route('/get_stored_credentials', methods=['POST'])
def get_stored_credentials():
    """
    Get stored credentials for a device (for debugging/admin purposes)
    """
    try:
        data = request.get_json()
        device_id = data.get('device_id')
        
        if not device_id:
            return jsonify({
                "status": "error",
                "message": "device_id is required"
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT usc.article_id, usc.domain, ar.request_string, usc.created_at
            FROM user_subscription_credentials usc
            JOIN article_requests ar ON usc.article_id = ar.article_id
            WHERE usc.device_id = %s
            ORDER BY usc.created_at DESC
        """, (device_id,))
        
        credentials = []
        for row in cursor.fetchall():
            article_id, domain, article_title, created_at = row
            credentials.append({
                'article_id': article_id,
                'domain': domain,
                'article_title': article_title,
                'submitted_at': created_at.isoformat() if created_at else None
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "device_id": device_id,
            "credentials_count": len(credentials),
            "credentials": credentials
        })
        
    except Exception as e:
        logging.error(f"Error getting stored credentials: {e}")
        return jsonify({
            "status": "error",
            "message": f"Failed to get credentials: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5019, debug=True)