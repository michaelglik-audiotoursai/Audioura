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
        
        # DEBUG: Log content before encoding
        logging.info(f"🔍 ORCHESTRATOR DEBUG: Storing article {article_id}")
        logging.info(f"🔍 Original article_text length: {len(article_text)} chars")
        logging.info(f"🔍 Article_text preview: {article_text[:200]}...")
        
        # Encode to UTF-8 bytes
        utf8_bytes = article_text.encode('utf-8')
        logging.info(f"🔍 UTF-8 encoded length: {len(utf8_bytes)} bytes")
        
        # Create article request
        cursor.execute("""
            INSERT INTO article_requests 
            (article_id, secret_id, request_string, article_text, status, created_at, started_at)
            VALUES (%s, %s, %s, %s, 'started', %s, %s)
        """, (article_id, secret_id, request_string, utf8_bytes, 
              datetime.now(), datetime.now()))
        
        # DEBUG: Verify what was stored
        cursor.execute("SELECT article_text FROM article_requests WHERE article_id = %s", (article_id,))
        stored_bytes = cursor.fetchone()[0]
        if hasattr(stored_bytes, 'tobytes'):
            stored_bytes = stored_bytes.tobytes()
        else:
            stored_bytes = bytes(stored_bytes)
        
        stored_text = stored_bytes.decode('utf-8')
        logging.info(f"🔍 Stored and retrieved length: {len(stored_text)} chars")
        logging.info(f"🔍 Storage integrity check: {stored_text == article_text}")
        logging.info(f"🔍 Retrieved preview: {stored_text[:200]}...")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Call news generator service
        logging.info(f"🔍 ORCHESTRATOR: About to call generator for {article_id}")
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
        # Get language parameter from query string
        language = request.args.get('language', 'en')
        
        # Validate language parameter
        supported_languages = ['en', 'ru', 'es', 'fr', 'de', 'zh']
        if language not in supported_languages:
            return jsonify({"error": f"Unsupported language: {language}. Supported: {supported_languages}"}), 400
        
        logging.info(f"Download request for article {article_id} in language: {language}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # If non-English language requested, check for existing translation or create one
        final_article_id = article_id
        if language != 'en':
            logging.info(f"Non-English language requested: {language}")
            
            # Check if translation already exists
            cursor.execute(
                "SELECT article_id FROM article_requests WHERE original_article_id = %s AND content_language = %s",
                (article_id, language)
            )
            existing_translation = cursor.fetchone()
            
            if existing_translation:
                final_article_id = existing_translation[0]
                logging.info(f"Found existing {language} translation: {final_article_id}")
            else:
                # Create translation using translation service
                try:
                    translation_data = {
                        "content_id": article_id,
                        "content_type": "article",
                        "languages": [language]
                    }
                    
                    logging.info(f"Calling translation service for article {article_id} -> {language}")
                    translation_response = requests.post(
                        "http://translation-service-1:5030/translate-with-audio",
                        headers={"Content-Type": "application/json"},
                        json=translation_data,
                        timeout=120
                    )
                    
                    if translation_response.status_code == 200:
                        translation_result = translation_response.json()
                        # Fix: Use correct field name from translation service response
                        translation_info = translation_result.get('translations', {}).get(language, {})
                        translated_article_id = translation_info.get('id')
                        
                        if translated_article_id:
                            final_article_id = translated_article_id
                            logging.info(f"Translation successful! Using translated article: {final_article_id}")
                        else:
                            logging.warning(f"Translation completed but no article ID returned, using English version")
                    else:
                        logging.error(f"Translation failed: {translation_response.status_code} - {translation_response.text}")
                        logging.info(f"Falling back to English version")
                        
                except Exception as translation_error:
                    logging.error(f"Translation error: {translation_error}")
                    logging.info(f"Falling back to English version")
        cursor.execute("""
            SELECT ar.subscription_required, ar.subscription_domain, ar.request_string
            FROM article_requests ar
            WHERE ar.article_id = %s
        """, (article_id,))
        
        subscription_info = cursor.fetchone()
        if not subscription_info:
            cursor.close()
            conn.close()
            return jsonify({"error": "Article not found"}), 404
        
        subscription_required, subscription_domain, article_title = subscription_info
        
        # CRITICAL SECURITY CHECK: Validate subscription credentials if required
        if subscription_required and subscription_domain:
            # Get user_id from request parameters or headers
            user_id = request.args.get('user_id') or request.headers.get('X-User-ID')
            
            if not user_id:
                cursor.close()
                conn.close()
                logging.warning(f"SECURITY BLOCK: No user_id provided for subscription article {article_id}")
                return jsonify({
                    "error": "Subscription required",
                    "message": f"This article requires a subscription to {subscription_domain}. Please provide credentials.",
                    "subscription_domain": subscription_domain,
                    "article_title": article_title
                }), 403
            
            # Check if user has VERIFIED credentials for this domain
            cursor.execute("""
                SELECT 1 FROM user_subscription_credentials 
                WHERE device_id = %s AND domain = %s AND verified_at IS NOT NULL
            """, (user_id, subscription_domain))
            
            has_verified_credentials = cursor.fetchone() is not None
            
            if not has_verified_credentials:
                cursor.close()
                conn.close()
                logging.warning(f"SECURITY BLOCK: User {user_id} has no verified credentials for {subscription_domain} - article {article_id}")
                return jsonify({
                    "error": "Subscription required",
                    "message": f"This article requires verified credentials for {subscription_domain}. Please submit valid subscription credentials.",
                    "subscription_domain": subscription_domain,
                    "article_title": article_title
                }), 403
            
            logging.info(f"SECURITY PASS: User {user_id} has verified credentials for {subscription_domain} - allowing access to article {article_id}")
        
        # Get news article from database (use final_article_id which may be translated)
        cursor.execute("""
            SELECT news_article, article_name, article_type 
            FROM news_audios 
            WHERE article_id = %s
        """, (final_article_id,))
        
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"error": "News article not found"}), 404
        
        news_article, article_name, article_type = result
        article_type = article_type or 'Others'
        
        cursor.close()
        conn.close()
        
        # Return ZIP file (use final_article_id for filename to distinguish translations)
        return send_file(
            io.BytesIO(news_article),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{final_article_id}.zip'
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