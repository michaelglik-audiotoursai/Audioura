import psycopg2
import requests
import uuid
import threading
import time
from datetime import datetime

SERVICE_VERSION = "1.2.2.82"

class BackgroundArticleProcessor:
    def __init__(self):
        self.processing_queue = []
        self.is_processing = False
        
    def queue_articles_for_processing(self, user_id, newsletter_source, article_links):
        """Queue articles for background processing"""
        for link in article_links:
            article_id = str(uuid.uuid4())
            
            # Store in article_requests table
            self.store_article_request(user_id, article_id, link, newsletter_source)
            
            # Add to processing queue
            self.processing_queue.append({
                'user_id': user_id,
                'article_id': article_id,
                'article_url': link,
                'newsletter_source': newsletter_source
            })
        
        # Start background processing if not already running
        if not self.is_processing:
            threading.Thread(target=self.process_queue, daemon=True).start()
        
        return {"queued_articles": len(article_links), "status": "processing_started"}
    
    def store_article_request(self, user_id, article_id, article_url, newsletter_source):
        """Store article request in database"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO article_requests 
            (secret_id, article_id, request_string, status, started_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, article_id, f"{newsletter_source}: {article_url}", 'queued', datetime.now()))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def process_queue(self):
        """Background processing of article queue"""
        self.is_processing = True
        
        while self.processing_queue:
            article_info = self.processing_queue.pop(0)
            
            try:
                # Update status to processing
                self.update_article_status(article_info['article_id'], 'processing')
                
                # Fetch article content
                article_content = self.fetch_article_content(article_info['article_url'])
                
                if article_content:
                    # Store article text
                    self.store_article_content(article_info['article_id'], article_content)
                    
                    # Request audio generation from news-orchestrator-1
                    audio_result = self.request_audio_generation(
                        article_info['article_id'], 
                        article_content
                    )
                    
                    if audio_result:
                        # Store audio info
                        self.store_news_audio(article_info['article_id'], article_content['title'])
                        self.update_article_status(article_info['article_id'], 'completed')
                    else:
                        self.update_article_status(article_info['article_id'], 'audio_failed')
                else:
                    self.update_article_status(article_info['article_id'], 'content_failed')
                    
            except Exception as e:
                print(f"Error processing article {article_info['article_id']}: {e}")
                self.update_article_status(article_info['article_id'], 'error')
            
            # Rate limiting
            time.sleep(2)
        
        self.is_processing = False
    
    def fetch_article_content(self, url):
        """Fetch and extract article content"""
        try:
            response = requests.get(url, timeout=15)
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'advertisement']):
                element.decompose()
            
            # Extract title
            title_elem = soup.find('title') or soup.find('h1')
            title = title_elem.get_text().strip() if title_elem else url
            
            # Extract content
            content_selectors = ['article', '.article-content', '.post-content', '.entry-content', 'main']
            content = ""
            
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    content = element.get_text(strip=True)
                    break
            
            if not content:
                content = soup.get_text(strip=True)
            
            # Validate content
            if len(content.split()) < 50:
                return None
                
            return {"title": title, "content": content}
            
        except Exception as e:
            print(f"Error fetching content from {url}: {e}")
            return None
    
    def store_article_content(self, article_id, article_content):
        """Store article content in database"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE article_requests 
            SET article_text = %s, article_topics = %s
            WHERE article_id = %s
        """, (article_content['content'].encode('utf-8'), len(article_content['content'].split()), article_id))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def request_audio_generation(self, article_id, article_content):
        """Request audio generation from news-orchestrator-1"""
        try:
            response = requests.post('http://news-orchestrator-1:5009/generate-article', 
                                   json={
                                       'article_text': article_content['content'],
                                       'request_string': article_content['title'],
                                       'secret_id': 'newsletter_user'
                                   }, timeout=60)
            
            return response.json() if response.status_code == 200 else None
            
        except Exception as e:
            print(f"Error requesting audio generation: {e}")
            return None
    
    def store_news_audio(self, article_id, article_title):
        """Store news audio record"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO news_audios (article_id, article_name, number_requested)
            VALUES (%s, %s, %s)
        """, (article_id, article_title, 1))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def update_article_status(self, article_id, status):
        """Update article processing status"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        cursor = conn.cursor()
        
        if status == 'completed':
            cursor.execute("""
                UPDATE article_requests 
                SET status = %s, finished_at = %s
                WHERE article_id = %s
            """, (status, datetime.now(), article_id))
        else:
            cursor.execute("""
                UPDATE article_requests 
                SET status = %s
                WHERE article_id = %s
            """, (status, article_id))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def get_user_articles(self, user_id):
        """Get processed articles for user (for Home page display)"""
        conn = psycopg2.connect(
            host="development-postgres-2-1",
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ar.article_id, ar.request_string, na.article_name, ar.status, ar.created_at
            FROM article_requests ar
            LEFT JOIN news_audios na ON ar.article_id = na.article_id
            WHERE ar.secret_id = %s AND ar.status = 'completed'
            ORDER BY ar.created_at DESC
        """, (user_id,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        articles = []
        for row in results:
            articles.append({
                'article_id': row[0],
                'newsletter_source': row[1].split(':')[0] if ':' in row[1] else 'Unknown',
                'article_title': row[2],
                'status': row[3],
                'created_at': row[4].isoformat()
            })
        
        return articles

if __name__ == "__main__":
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    processor = BackgroundArticleProcessor()
    
    @app.route('/queue_articles', methods=['POST'])
    def queue_articles():
        data = request.json
        result = processor.queue_articles_for_processing(
            data['user_id'],
            data['newsletter_source'], 
            data['article_links']
        )
        return jsonify(result)
    
    @app.route('/get_user_articles/<user_id>', methods=['GET'])
    def get_user_articles(user_id):
        articles = processor.get_user_articles(user_id)
        return jsonify(articles)
    
    app.run(host='0.0.0.0', port=5015)