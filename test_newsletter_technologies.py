#!/usr/bin/env python3
"""
Newsletter Technologies Comprehensive Test
Tests different newsletter platforms and content types
"""
import requests
import json
import psycopg2
from datetime import datetime

def cleanup_test_newsletter(url):
    """Clean up test newsletter and all associated articles"""
    try:
        conn = psycopg2.connect(
            host='localhost', database='audiotours', user='admin', 
            password='password123', port='5433'
        )
        cursor = conn.cursor()
        
        # Get newsletter ID
        cursor.execute("SELECT id FROM newsletters WHERE url = %s", (url,))
        result = cursor.fetchone()
        if not result:
            print(f"No newsletter found for URL: {url}")
            return
        
        newsletter_id = result[0]
        
        # Clean up in proper order (foreign key constraints)
        cursor.execute("""
            DELETE FROM news_audios WHERE article_id IN (
                SELECT nar.article_requests_id FROM newsletters_article_link nar 
                WHERE nar.newsletters_id = %s
            )
        """, (newsletter_id,))
        
        cursor.execute("DELETE FROM newsletters_article_link WHERE newsletters_id = %s", (newsletter_id,))
        
        cursor.execute("""
            DELETE FROM article_requests WHERE article_id IN (
                SELECT nar.article_requests_id FROM newsletters_article_link nar 
                WHERE nar.newsletters_id = %s
            )
        """, (newsletter_id,))
        
        cursor.execute("DELETE FROM newsletters WHERE id = %s", (newsletter_id,))
        
        conn.commit()
        print(f"SUCCESS: Cleaned up newsletter and associated articles")
        
    except Exception as e:
        print(f"ERROR: Database cleanup error: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def test_newsletter_processing(newsletter_url, newsletter_name, expected_min_articles=1):
    """Test newsletter processing end-to-end"""
    print(f"\n{'='*60}")
    print(f"TESTING: {newsletter_name}")
    print(f"URL: {newsletter_url}")
    print(f"{'='*60}")
    
    # Step 1: Cleanup
    print("=== STEP 1: Database Cleanup ===")
    cleanup_test_newsletter(newsletter_url)
    
    # Step 2: Process Newsletter
    print("=== STEP 2: Newsletter Processing ===")
    try:
        payload = {
            "newsletter_url": newsletter_url,
            "user_id": "test_user_newsletter",
            "max_articles": 10
        }
        
        print(f"Sending request to newsletter processor...")
        response = requests.post(
            "http://localhost:5017/process_newsletter",
            json=payload,
            timeout=120
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"SUCCESS: Newsletter processed")
            print(f"Newsletter ID: {result.get('newsletter_id', 'N/A')}")
            print(f"Articles created: {result.get('articles_created', 0)}")
            
            # Save debug info
            debug_file = f"debug_{newsletter_name.lower().replace(' ', '_')}_response.json"
            with open(debug_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"Response saved to: {debug_file}")
            
            return result
        else:
            print(f"FAILED: HTTP {response.status_code}")
            print(f"Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"ERROR: Newsletter processing failed: {e}")
        return None

def verify_newsletter_articles(newsletter_url, newsletter_name):
    """Verify articles were created and stored properly"""
    print("=== STEP 3: Database Verification ===")
    try:
        conn = psycopg2.connect(
            host='localhost', database='audiotours', user='admin', 
            password='password123', port='5433'
        )
        cursor = conn.cursor()
        
        # Get newsletter and articles
        cursor.execute("""
            SELECT n.id, n.name, COUNT(nar.article_requests_id) as article_count
            FROM newsletters n
            LEFT JOIN newsletters_article_link nar ON n.id = nar.newsletters_id
            WHERE n.url = %s
            GROUP BY n.id, n.name
        """, (newsletter_url,))
        
        result = cursor.fetchone()
        if not result:
            print("ERROR: No newsletter found in database")
            return False
        
        newsletter_id, name, article_count = result
        print(f"SUCCESS: Newsletter '{name}' found with {article_count} articles")
        
        # Get article details
        cursor.execute("""
            SELECT ar.article_id, ar.request_string, ar.status, 
                   LENGTH(ar.article_text) as content_length
            FROM article_requests ar
            JOIN newsletters_article_link nar ON ar.article_id = nar.article_requests_id
            WHERE nar.newsletters_id = %s
            ORDER BY ar.created_at DESC
        """, (newsletter_id,))
        
        articles = cursor.fetchall()
        print(f"\nArticle Details:")
        for i, (article_id, title, status, length) in enumerate(articles, 1):
            print(f"  {i}. {title[:50]}...")
            print(f"     ID: {article_id}")
            print(f"     Status: {status}")
            print(f"     Content: {length} chars")
            
            if status == 'finished' and length > 100:
                print(f"     ZIP: curl -X GET \"http://localhost:5012/download/{article_id}\" -o \"{newsletter_name.lower().replace(' ', '_')}_{i}.zip\"")
        
        return article_count > 0
        
    except Exception as e:
        print(f"ERROR: Database verification failed: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def main():
    """Run comprehensive newsletter technology tests"""
    print("NEWSLETTER TECHNOLOGIES COMPREHENSIVE TEST")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")
    
    # Test different newsletter technologies
    test_cases = [
        {
            "url": "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines",
            "name": "Guy Raz Substack",
            "expected_articles": 8
        },
        {
            "url": "https://mailchi.mp/bostonglobe.com/todaysheadlines-6057237",
            "name": "Boston Globe MailChimp",
            "expected_articles": 5
        },
        {
            "url": "https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717",
            "name": "Quora Newsletter",
            "expected_articles": 3
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        try:
            # Process newsletter
            result = test_newsletter_processing(
                test_case["url"], 
                test_case["name"], 
                test_case["expected_articles"]
            )
            
            # Verify results
            if result:
                verified = verify_newsletter_articles(test_case["url"], test_case["name"])
                results.append({
                    "name": test_case["name"],
                    "url": test_case["url"],
                    "success": verified,
                    "articles_created": result.get("articles_created", 0),
                    "expected": test_case["expected_articles"]
                })
            else:
                results.append({
                    "name": test_case["name"],
                    "url": test_case["url"],
                    "success": False,
                    "articles_created": 0,
                    "expected": test_case["expected_articles"]
                })
                
        except Exception as e:
            print(f"ERROR: Test failed for {test_case['name']}: {e}")
            results.append({
                "name": test_case["name"],
                "url": test_case["url"],
                "success": False,
                "error": str(e),
                "articles_created": 0,
                "expected": test_case["expected_articles"]
            })
    
    # Generate summary
    print(f"\n{'='*60}")
    print("NEWSLETTER TECHNOLOGIES TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for r in results if r['success'])
    total = len(results)
    
    print(f"Total Newsletter Types: {total}")
    print(f"Successful: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
    
    print(f"\nDetailed Results:")
    for result in results:
        status = "PASS" if result['success'] else "FAIL"
        articles = result['articles_created']
        expected = result['expected']
        print(f"  {status} {result['name']}: {articles}/{expected} articles")
        if 'error' in result:
            print(f"       Error: {result['error']}")
    
    # Save results
    report_file = f"newsletter_tech_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump({
            'summary': {
                'total_tests': total,
                'passed': passed,
                'failed': total - passed,
                'success_rate': (passed/total*100) if total > 0 else 0,
                'timestamp': datetime.now().isoformat()
            },
            'results': results
        }, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_file}")
    
    return total - passed

if __name__ == "__main__":
    failures = main()
    exit(failures)