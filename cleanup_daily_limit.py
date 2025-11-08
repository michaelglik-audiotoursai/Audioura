#!/usr/bin/env python3
"""
Daily Limit Cleanup Utility
Removes newsletter records to bypass daily processing limits for testing
"""
import psycopg2
import urllib.parse
import logging

logging.basicConfig(level=logging.INFO)

def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        database='audiotours', 
        user='admin',
        password='password123',
        port='5433'
    )

def clean_url(url):
    """Clean URL same way as newsletter processor"""
    try:
        parsed = urllib.parse.urlparse(url)
        # For Apple Podcasts, preserve episode ID
        if 'podcasts.apple.com' in parsed.netloc and '?i=' in url:
            import re
            episode_match = re.search(r'i=([^&]+)', parsed.query)
            if episode_match:
                episode_id = episode_match.group(1)
                return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', f'i={episode_id}', ''))
        
        # For all others, remove query parameters
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    except:
        return url

def remove_daily_limit(url):
    """Remove newsletter record to bypass daily limit"""
    clean_newsletter_url = clean_url(url)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if newsletter exists
        cursor.execute("SELECT id, created_at FROM newsletters WHERE url = %s", (clean_newsletter_url,))
        existing = cursor.fetchone()
        
        if existing:
            newsletter_id, created_at = existing
            print(f"Found newsletter ID {newsletter_id} created at {created_at}")
            
            # Delete newsletter (cascade will handle linked articles)
            cursor.execute("DELETE FROM newsletters WHERE id = %s", (newsletter_id,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            cursor.close()
            conn.close()
            
            if deleted_count > 0:
                print(f"SUCCESS: Newsletter record deleted, daily limit bypassed")
                return True
            else:
                print(f"WARNING: Newsletter record not found")
                return False
        else:
            print(f"INFO: Newsletter not processed today")
            cursor.close()
            conn.close()
            return True
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_quora_with_cleanup():
    """Test Quora URL with proper cleanup and encoding"""
    quora_url = "https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717"
    
    print("=== QUORA NEWSLETTER TEST WITH CLEANUP ===")
    print(f"URL: {quora_url}")
    
    # Step 1: Remove daily limit
    print("\nStep 1: Removing daily limit...")
    if remove_daily_limit(quora_url):
        print("SUCCESS: Daily limit removed")
    else:
        print("ERROR: Failed to remove daily limit")
        return
    
    # Step 2: Create proper JSON payload
    import json
    payload = {
        "newsletter_url": quora_url,
        "user_id": "test_user_quora", 
        "max_articles": 5
    }
    
    print(f"\nStep 2: Testing with payload:")
    print(json.dumps(payload, indent=2))
    
    # Step 3: Save to file for curl command
    with open('test_quora_clean.json', 'w') as f:
        json.dump(payload, f, indent=2)
    
    print(f"\nStep 3: Run this command to test:")
    print(f"curl -X POST http://localhost:5017/process_newsletter -H \"Content-Type: application/json\" -d @test_quora_clean.json")
    
    return payload

if __name__ == "__main__":
    # Test the problematic Quora URL
    test_quora_with_cleanup()