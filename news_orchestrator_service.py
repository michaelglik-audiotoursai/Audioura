#!/usr/bin/env python3
"""
News Orchestrator Service - Coordinates article processing workflow
"""
import os
import sys
import psycopg2
from flask import Flask, request, jsonify, send_file
import uuid
import logging
import requests
from datetime import datetime
import io

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Force unbuffered output for real-time logs
import sys
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

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
    return jsonify({"status": "healthy", "service": "news_orchestrator_1"})

@app.route('/generate-news', methods=['POST'])
def generate_news():
    try:
        data = request.get_json()
        article_text = data.get('article_text', '')
        request_string = data.get('request_string', 'News Article')
        secret_id = data.get('secret_id', 'anonymous')
        major_points_count = data.get('major_points_count', 0)
        
        if not article_text:
            return jsonify({"error": "Article text is required"}), 400
        
        # Generate unique article ID
        article_id = str(uuid.uuid4())
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create article request
        cursor.execute("""
            INSERT INTO article_requests 
            (article_id, secret_id, request_string, article_text, status, created_at, started_at)
            VALUES (%s, %s, %s, %s, 'started', %s, %s)
        """, (article_id, secret_id, request_string, article_text.encode('utf-8'), 
              datetime.now(), datetime.now()))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Call news generator service
        logging.info(f'Calling news generator for article {article_id} with {major_points_count} major points')
        generator_response = requests.post(
            f'http://news-generator-1:5010/process-article/{article_id}',
            json={'max_major_points': major_points_count},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        logging.info(f'Generator response: {generator_response.status_code}')
        if generator_response.status_code != 200:
            logging.error(f'Generator failed: {generator_response.text}')
            raise Exception(f"News generator failed: {generator_response.text}")
        
        # Call news processor service
        logging.info(f'Calling news processor for article {article_id}')
        processor_response = requests.post(
            f'http://news-processor-1:5011/process-audio/{article_id}',
            timeout=120
        )
        
        logging.info(f'Processor response: {processor_response.status_code}')
        if processor_response.status_code != 200:
            logging.error(f'Processor failed: {processor_response.text}')
            raise Exception(f"News processor failed: {processor_response.text}")
        
        logging.info(f'News generation completed successfully for {article_id}')
        
        return jsonify({
            "status": "success",
            "article_id": article_id,
            "message": "News article processed successfully"
        })
        
    except Exception as e:
        logging.error(f"Error in news orchestration: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/<article_id>', methods=['GET'])
def download_news(article_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get news article from database
        cursor.execute("""
            SELECT news_article, article_name, article_type 
            FROM news_audios 
            WHERE article_id = %s
        """, (article_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "News article not found"}), 404
        
        news_article, article_name, article_type = result
        article_type = article_type or 'Others'
        
        cursor.close()
        conn.close()
        
        # Return ZIP file
        return send_file(
            io.BytesIO(news_article),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{article_id}.zip'
        )
        
    except Exception as e:
        logging.error(f"Error downloading news {article_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/status/<article_id>', methods=['GET'])
def get_status(article_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT status, created_at, started_at, finished_at, request_string
            FROM article_requests 
            WHERE article_id = %s
        """, (article_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Article not found"}), 404
        
        status, created_at, started_at, finished_at, request_string = result
        
        cursor.close()
        conn.close()
        
        # Map status for mobile app compatibility
        mobile_status = 'completed' if status == 'finished' else status
        
        return jsonify({
            "status": mobile_status,
            "article_id": article_id,
            "request_string": request_string,
            "created_at": created_at.isoformat() if created_at else None,
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
            "progress": get_progress_message(status)
        })
        
    except Exception as e:
        logging.error(f"Error getting status for {article_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

def get_progress_message(status):
    messages = {
        'started': 'Processing article text...',
        'ready': 'Converting to audio...',
        'finished': 'Article ready for download!',
        'error': 'Processing failed'
    }
    return messages.get(status, 'Unknown status')

@app.route('/articles', methods=['GET'])
def get_articles():
    """Get all available articles with types for mobile app"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get articles that are finished and have audio
        cursor.execute("""
            SELECT na.article_id, na.article_name, na.article_type, na.created_at,
                   ar.request_string
            FROM news_audios na
            JOIN article_requests ar ON na.article_id = ar.article_id
            WHERE ar.status = 'finished'
            ORDER BY na.created_at DESC
            LIMIT 50
        """)
        
        results = cursor.fetchall()
        articles = []
        
        for result in results:
            article_id, article_name, article_type, created_at, request_string = result
            articles.append({
                'article_id': article_id,
                'title': article_name or request_string,
                'article_type': article_type or 'Others',
                'created_at': created_at.isoformat() if created_at else None
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'articles': articles,
            'total': len(articles)
        })
        
    except Exception as e:
        logging.error(f"Error getting articles: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5012, debug=True)