#!/usr/bin/env python3
"""
Comprehensive Apple Podcasts Processing Test
Tests the complete flow from URL to final article with debugging at each step
"""
import requests
import json
import psycopg2
import os
from datetime import datetime

# Test URL from Guy Raz newsletter
TEST_APPLE_URL = "https://podcasts.apple.com/us/podcast/babylist-natalie-gordon-how-a-new-mom-used-nap-time/id1150510297?i=1000733348575"
TEST_USER_ID = "test_user_apple"

# Test cleanup prevents storage growth by removing old test articles

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def cleanup_existing_articles():
    """Clean up test articles to maintain constant storage"""
    print("=== STEP 1: Database Cleanup ===")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Clean up all test articles (not just this URL)
        cursor.execute("""
            DELETE FROM news_audios WHERE article_id LIKE 'test-%';
            DELETE FROM newsletters_article_link WHERE article_requests_id LIKE 'test-%';
            DELETE FROM article_requests WHERE article_id LIKE 'test-%' OR url = %s;
        """, (TEST_APPLE_URL,))
        
        conn.commit()
        print("SUCCESS: Cleaned up all test articles")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: Database cleanup error: {e}")

def test_apple_processor_direct():
    """Test Apple Podcasts processor directly"""
    print("\n=== STEP 2: Direct Apple Podcasts Processor Test ===")
    
    try:
        from apple_podcasts_processor import process_apple_podcasts_url
        
        print(f"Testing URL: {TEST_APPLE_URL}")
        result = process_apple_podcasts_url(TEST_APPLE_URL)
        
        # Save result to file
        with open('debug_apple_processor_output.json', 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"SUCCESS: Apple processor result saved to debug_apple_processor_output.json")
        print(f"Result keys: {list(result.keys())}")
        
        if result.get('success'):
            print(f"SUCCESS: Title='{result.get('title', 'N/A')}'")
            print(f"SUCCESS: Content length: {len(result.get('content', ''))} chars")
            print(f"SUCCESS: Content preview: {result.get('content', '')[:200]}...")
        else:
            print(f"FAILED: {result.get('error', 'Unknown error')}")
        
        return result
        
    except Exception as e:
        print(f"ERROR: Apple processor error: {e}")
        return None

def test_news_orchestrator():
    """Test news orchestrator with Apple Podcasts content"""
    print("\n=== STEP 3: News Orchestrator Test ===")
    
    # First get content from Apple processor
    apple_result = test_apple_processor_direct()
    if not apple_result or not apple_result.get('success'):
        print("ERROR: Cannot test orchestrator - Apple processor failed")
        return None
    
    try:
        # Prepare orchestrator payload
        payload = {
            'article_text': apple_result['content'],
            'request_string': apple_result['title'],
            'secret_id': TEST_USER_ID,
            'major_points_count': 4
        }
        
        # Save input payload
        with open('debug_apple_orchestrator_input.json', 'w') as f:
            json.dump(payload, f, indent=2)
        
        print(f"SUCCESS: Orchestrator input saved to debug_apple_orchestrator_input.json")
        print(f"Input - Title: '{payload['request_string']}'")
        print(f"Input - Content length: {len(payload['article_text'])} chars")
        
        # Call orchestrator
        response = requests.post(
            'http://localhost:5012/generate-news',
            json=payload,
            timeout=180,
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )
        
        print(f"SUCCESS: Orchestrator response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            # Save output
            with open('debug_apple_orchestrator_output.json', 'w') as f:
                json.dump(result, f, indent=2)
            
            print(f"SUCCESS: Orchestrator output saved to debug_apple_orchestrator_output.json")
            print(f"SUCCESS: Created article_id: {result.get('article_id', 'N/A')}")
            
            return result
        else:
            error_text = response.text
            with open('debug_apple_orchestrator_error.txt', 'w') as f:
                f.write(f"Status: {response.status_code}\n")
                f.write(f"Response: {error_text}\n")
            
            print(f"ERROR: Orchestrator failed: HTTP {response.status_code}")
            print(f"ERROR: Error saved to debug_apple_orchestrator_error.txt")
            return None
            
    except Exception as e:
        print(f"ERROR: Orchestrator test error: {e}")
        return None

def test_final_article_content():
    """Check what was actually stored in the database"""
    print("\n=== STEP 4: Final Article Content Check ===")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT article_id, request_string, LENGTH(article_text) as content_length, 
                   LEFT(CONVERT_FROM(article_text, 'UTF8'), 200) as content_preview, status
            FROM article_requests 
            WHERE url = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (TEST_APPLE_URL,))
        
        result = cursor.fetchone()
        
        if result:
            article_id, title, content_length, preview, status = result
            
            print(f"SUCCESS: Found article in database:")
            print(f"  Article ID: {article_id}")
            print(f"  Title: {title}")
            print(f"  Content length: {content_length} chars")
            print(f"  Status: {status}")
            print(f"  Preview: {preview}...")
            
            # Save full content to file
            cursor.execute("SELECT article_text FROM article_requests WHERE article_id = %s", (article_id,))
            article_bytes = cursor.fetchone()[0]
            if hasattr(article_bytes, 'tobytes'):
                article_bytes = article_bytes.tobytes()
            full_content = article_bytes.decode('utf-8')
            
            with open('debug_apple_final_article_content.txt', 'w', encoding='utf-8') as f:
                f.write(f"Article ID: {article_id}\n")
                f.write(f"URL: {TEST_APPLE_URL}\n")
                f.write(f"Title: {title}\n")
                f.write(f"Content Length: {content_length} chars\n")
                f.write(f"Status: {status}\n")
                f.write(f"Created: {datetime.now()}\n")
                f.write(f"\n=== FULL CONTENT ===\n")
                f.write(full_content)
            
            print(f"SUCCESS: Full content saved to debug_apple_final_article_content.txt")
            
        else:
            print("ERROR: No article found in database")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: Database check error: {e}")

def main():
    """Run complete Apple Podcasts processing test"""
    print("APPLE PODCASTS PROCESSING COMPREHENSIVE TEST")
    print("=" * 50)
    
    # Step 1: Cleanup
    cleanup_existing_articles()
    
    # Step 2: Test Apple processor
    apple_result = test_apple_processor_direct()
    
    # Step 3: Test orchestrator
    orchestrator_result = test_news_orchestrator()
    
    # Step 4: Check final result
    test_final_article_content()
    
    print("\n" + "=" * 50)
    print("APPLE PODCASTS TEST COMPLETE")
    
    # Show download command if orchestrator succeeded
    if orchestrator_result and orchestrator_result.get('article_id'):
        article_id = orchestrator_result['article_id']
        print("\nZIP FILE DOWNLOAD COMMAND:")
        print(f'curl -X GET "http://localhost:5012/download/{article_id}" -o "apple_podcasts_test.zip"')
        print("\nVERIFY ZIP CONTENTS:")
        print("unzip -l apple_podcasts_test.zip")
        print("\nNOTE: Test cleanup prevents storage growth by removing old test articles.")
    
    print("\nCheck debug files for detailed analysis:")
    print("  - debug_apple_processor_output.json")
    print("  - debug_apple_orchestrator_input.json")
    print("  - debug_apple_orchestrator_output.json")
    print("  - debug_apple_final_article_content.txt")

if __name__ == "__main__":
    main()