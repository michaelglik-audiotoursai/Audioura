import psycopg2
from openai import OpenAI
import os
import numpy as np

SERVICE_VERSION = "1.2.2.1"

class NewsSearchService:
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def search_articles(self, user_id, search_query):
        # Generate embedding for search query
        query_embedding = self.openai_client.embeddings.create(
            input=search_query,
            model="text-embedding-ada-002"
        ).data[0].embedding
        
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password"
        )
        
        cursor = conn.cursor()
        
        # Vector similarity search
        cursor.execute("""
            SELECT id, newsletter_source, article_title, audio_file_path, created_at,
                   (content_vector <=> %s::vector) as similarity
            FROM news_audios 
            WHERE user_id = %s
            ORDER BY similarity ASC
            LIMIT 10
        """, (query_embedding, user_id))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        articles = []
        for row in results:
            articles.append({
                'id': row[0],
                'newsletter_source': row[1],
                'article_title': row[2],
                'audio_file_path': row[3],
                'created_at': row[4].isoformat(),
                'similarity_score': float(row[5])
            })
        
        return articles
    
    def get_user_news_articles(self, user_id):
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT newsletter_source, article_title, audio_file_path, created_at
            FROM news_audios 
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Group by newsletter source
        newsletters = {}
        for row in results:
            source = row[0]
            if source not in newsletters:
                newsletters[source] = []
            
            newsletters[source].append({
                'title': row[1],
                'audio_file_path': row[2],
                'created_at': row[3].isoformat()
            })
        
        return newsletters

if __name__ == "__main__":
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    search_service = NewsSearchService()
    
    @app.route('/search_articles', methods=['POST'])
    def search_articles():
        data = request.json
        results = search_service.search_articles(data['user_id'], data['search_query'])
        return jsonify(results)
    
    @app.route('/get_user_articles/<user_id>', methods=['GET'])
    def get_user_articles(user_id):
        results = search_service.get_user_news_articles(user_id)
        return jsonify(results)
    
    app.run(host='0.0.0.0', port=5001)