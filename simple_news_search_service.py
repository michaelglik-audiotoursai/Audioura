import psycopg2
import re

SERVICE_VERSION = "1.2.2.82"

class SimpleNewsSearchService:
    def __init__(self):
        pass
    
    def search_articles(self, user_id, search_query):
        """Simple database text search - no expensive embeddings"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password"
        )
        
        cursor = conn.cursor()
        
        # Simple text search using PostgreSQL full-text search
        search_terms = search_query.lower().split()
        
        # Build search condition
        search_conditions = []
        params = [user_id]
        
        for i, term in enumerate(search_terms):
            search_conditions.append(f"(LOWER(CONVERT_FROM(ar.article_text, 'UTF8')) LIKE %s OR LOWER(na.article_name) LIKE %s)")
            params.extend([f'%{term}%', f'%{term}%'])
        
        where_clause = " AND ".join(search_conditions)
        
        query = f"""
            SELECT ar.article_id, ar.request_string, na.article_name, ar.created_at,
                   LENGTH(CONVERT_FROM(ar.article_text, 'UTF8')) as content_length
            FROM article_requests ar
            JOIN news_audios na ON ar.article_id = na.article_id
            WHERE ar.secret_id = %s AND ar.status = 'completed'
            AND ({where_clause})
            ORDER BY ar.created_at DESC
            LIMIT 20
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        articles = []
        for row in results:
            articles.append({
                'article_id': row[0],
                'newsletter_source': row[1].split(':')[0] if ':' in row[1] else 'Unknown',
                'article_title': row[2],
                'created_at': row[3].isoformat(),
                'content_length': row[4]
            })
        
        return articles
    
    def search_by_newsletter_source(self, user_id, newsletter_source):
        """Search articles by newsletter source"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ar.article_id, ar.request_string, na.article_name, ar.created_at
            FROM article_requests ar
            JOIN news_audios na ON ar.article_id = na.article_id
            WHERE ar.secret_id = %s AND ar.status = 'completed'
            AND LOWER(ar.request_string) LIKE %s
            ORDER BY ar.created_at DESC
        """, (user_id, f'%{newsletter_source.lower()}%'))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        articles = []
        for row in results:
            articles.append({
                'article_id': row[0],
                'newsletter_source': row[1].split(':')[0] if ':' in row[1] else 'Unknown',
                'article_title': row[2],
                'created_at': row[3].isoformat()
            })
        
        return articles
    
    def search_by_date_range(self, user_id, start_date, end_date):
        """Search articles by date range"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ar.article_id, ar.request_string, na.article_name, ar.created_at
            FROM article_requests ar
            JOIN news_audios na ON ar.article_id = na.article_id
            WHERE ar.secret_id = %s AND ar.status = 'completed'
            AND ar.created_at BETWEEN %s AND %s
            ORDER BY ar.created_at DESC
        """, (user_id, start_date, end_date))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        articles = []
        for row in results:
            articles.append({
                'article_id': row[0],
                'newsletter_source': row[1].split(':')[0] if ':' in row[1] else 'Unknown',
                'article_title': row[2],
                'created_at': row[3].isoformat()
            })
        
        return articles
    
    def get_newsletter_sources(self, user_id):
        """Get all newsletter sources for user"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT SPLIT_PART(ar.request_string, ':', 1) as newsletter_source,
                   COUNT(*) as article_count
            FROM article_requests ar
            WHERE ar.secret_id = %s AND ar.status = 'completed'
            GROUP BY SPLIT_PART(ar.request_string, ':', 1)
            ORDER BY article_count DESC
        """, (user_id,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        sources = []
        for row in results:
            sources.append({
                'newsletter_source': row[0],
                'article_count': row[1]
            })
        
        return sources

if __name__ == "__main__":
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    search_service = SimpleNewsSearchService()
    
    @app.route('/search_articles', methods=['POST'])
    def search_articles():
        data = request.json
        results = search_service.search_articles(data['user_id'], data['search_query'])
        return jsonify(results)
    
    @app.route('/search_by_source', methods=['POST'])
    def search_by_source():
        data = request.json
        results = search_service.search_by_newsletter_source(data['user_id'], data['newsletter_source'])
        return jsonify(results)
    
    @app.route('/get_newsletter_sources/<user_id>', methods=['GET'])
    def get_newsletter_sources(user_id):
        sources = search_service.get_newsletter_sources(user_id)
        return jsonify(sources)
    
    app.run(host='0.0.0.0', port=5016)
