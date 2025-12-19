#!/usr/bin/env python3
"""
Translation Service - AudioTours Multi-Language Support
Port: 5030
"""

from flask import Flask, request, jsonify, make_response
import boto3
import zipfile
import io
import uuid
import psycopg2
import logging
from concurrent.futures import ThreadPoolExecutor
import os
import json

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

class TranslationService:
    def __init__(self):
        self.translate_client = boto3.client('translate', region_name='us-east-1')
        self.polly_client = boto3.client('polly', region_name='us-east-1')
        self.executor = ThreadPoolExecutor(max_workers=5)
        
    def get_db_connection(self):
        return psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password"
        )
    
    def translate_text(self, text, target_language):
        """Translate text using AWS Translate"""
        if target_language == 'en':
            return text
            
        try:
            response = self.translate_client.translate_text(
                Text=text[:5000],  # AWS limit
                SourceLanguageCode='en',
                TargetLanguageCode=target_language
            )
            return response['TranslatedText']
        except Exception as e:
            logging.error(f"Translation error: {e}")
            return text
    
    def generate_audio(self, text, target_language):
        """Generate audio using AWS Polly"""
        voice_map = {
            'en': 'Joanna',
            'es': 'Lucia',
            'fr': 'Celine', 
            'de': 'Marlene',
            'ru': 'Tatyana',
            'zh': 'Zhiyu'
        }
        
        try:
            response = self.polly_client.synthesize_speech(
                Text=text[:3000],  # AWS limit
                OutputFormat='mp3',
                VoiceId=voice_map.get(target_language, 'Joanna')
            )
            return response['AudioStream'].read()
        except Exception as e:
            logging.error(f"Audio generation error: {e}")
            return None
    
    def translate_tour(self, original_tour_id, target_language):
        """Translate a tour to target language"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get original tour
            cursor.execute("SELECT * FROM audio_tours WHERE id = %s", (original_tour_id,))
            original_tour = cursor.fetchone()
            if not original_tour:
                return None
            
            # Check if translation already exists
            cursor.execute(
                "SELECT id FROM audio_tours WHERE original_tour_id = %s AND language = %s",
                (original_tour_id, target_language)
            )
            existing = cursor.fetchone()
            if existing:
                return existing[0]
            
            # Translate tour name
            translated_name = self.translate_text(original_tour[1], target_language)
            translated_request = self.translate_text(original_tour[2], target_language)
            
            # Create new tour record
            cursor.execute("""
                INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, 
                                       lat, lng, language, original_tour_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (
                translated_name, translated_request, original_tour[3], original_tour[4],
                original_tour[5], original_tour[6], target_language, original_tour_id
            ))
            
            new_tour_id = cursor.fetchone()[0]
            conn.commit()
            
            logging.info(f"Created translated tour {new_tour_id} in {target_language}")
            return new_tour_id
            
        except Exception as e:
            logging.error(f"Tour translation error: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def translate_article(self, original_article_id, target_language):
        """Translate an article to target language"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get original article
            cursor.execute("SELECT * FROM article_requests WHERE article_id = %s", (original_article_id,))
            original_article = cursor.fetchone()
            if not original_article:
                return None
            
            # Check if translation already exists
            cursor.execute(
                "SELECT article_id FROM article_requests WHERE original_article_id = %s AND language = %s",
                (original_article_id, target_language)
            )
            existing = cursor.fetchone()
            if existing:
                return existing[0]
            
            # Translate content
            translated_text = self.translate_text(original_article[1], target_language)
            translated_title = self.translate_text(original_article[2], target_language)
            
            # Create new article record
            new_article_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO article_requests (article_id, article_text, request_string, url, 
                                            status, language, original_article_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()) RETURNING article_id
            """, (
                new_article_id, translated_text, translated_title, original_article[3],
                'finished', target_language, original_article_id
            ))
            
            conn.commit()
            logging.info(f"Created translated article {new_article_id} in {target_language}")
            return new_article_id
            
        except Exception as e:
            logging.error(f"Article translation error: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

# Initialize translation service
translation_service = TranslationService()

def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.after_request
def after_request(response):
    return add_cors_headers(response)

@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    if request.method == 'OPTIONS':
        return make_response()
    return jsonify({"status": "healthy", "service": "translation"})

@app.route('/translate', methods=['POST', 'OPTIONS'])
def translate_content():
    if request.method == 'OPTIONS':
        return make_response()
    
    data = request.json
    content_id = data.get('content_id')
    content_type = data.get('content_type')  # 'tour' or 'article'
    languages = data.get('languages', ['en'])
    
    results = {}
    for lang in languages:
        if lang == 'en':
            results[lang] = {'status': 'original', 'id': content_id}
            continue
            
        if content_type == 'tour':
            translated_id = translation_service.translate_tour(content_id, lang)
        else:
            translated_id = translation_service.translate_article(content_id, lang)
        
        if translated_id:
            results[lang] = {'status': 'translated', 'id': translated_id}
        else:
            results[lang] = {'status': 'failed', 'id': None}
    
    return jsonify({
        'status': 'completed',
        'translations': results
    })

@app.route('/supported-languages', methods=['GET', 'OPTIONS'])
def get_supported_languages():
    if request.method == 'OPTIONS':
        return make_response()
    
    conn = translation_service.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM supported_languages WHERE enabled = TRUE ORDER BY language_code")
        languages = cursor.fetchall()
        
        result = []
        for lang in languages:
            result.append({
                'code': lang[0],
                'name': lang[1],
                'voice': lang[2],
                'enabled': lang[3]
            })
        
        return jsonify({'languages': result})
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5030, debug=True)