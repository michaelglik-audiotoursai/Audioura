#!/usr/bin/env python3
"""
Test Guy Raz newsletter processing with the Unicode fix
"""
import requests
import json
import time

def test_guy_raz_newsletter():
    """Test Guy Raz newsletter processing end-to-end"""
    
    newsletter_url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom"
    
    print("=== GUY RAZ NEWSLETTER TEST (FIXED) ===")
    print(f"URL: {newsletter_url}")
    
    # Clean up any existing newsletter first
    print("Cleaning up existing newsletter...")
    try:
        cleanup_response = requests.post(
            'http://localhost:5017/cleanup_newsletter',
            json={"newsletter_url": newsletter_url},
            timeout=30
        )
        print(f"Cleanup response: {cleanup_response.status_code}")
    except:
        print("Cleanup not available, proceeding...")
    
    # Process newsletter
    print("Processing newsletter...")
    payload = {
        "newsletter_url": newsletter_url,
        "user_id": "test_user",
        "max_articles": 10
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/process_newsletter',
            json=payload,
            timeout=300
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Status: {result['status']}")
            print(f"Newsletter ID: {result.get('newsletter_id')}")
            print(f"Articles found: {result.get('articles_found')}")
            print(f"Articles created: {result.get('articles_created')}")
            print(f"Articles failed: {result.get('articles_failed')}")
            
            if result.get('failed_articles'):
                print("Failed articles:")
                for failed in result['failed_articles']:
                    print(f"  - {failed['url']}: {failed['error']}")
            
            # Get newsletter articles
            if result.get('newsletter_id'):
                print(f"\nGetting articles for newsletter {result['newsletter_id']}...")
                articles_response = requests.post(
                    'http://localhost:5017/get_articles_by_newsletter_id',
                    json={"newsletter_id": result['newsletter_id']},
                    timeout=30
                )
                
                if articles_response.status_code == 200:
                    articles_result = articles_response.json()
                    print(f"Articles retrieved: {len(articles_result.get('articles', []))}")
                    
                    for i, article in enumerate(articles_result.get('articles', []), 1):
                        print(f"{i}. {article['title']} ({article['article_id']})")
                        print(f"   URL: {article['url']}")
                        print(f"   Date: {article['date']}")
                        
                        # Test ZIP file generation
                        print(f"   Testing ZIP generation...")
                        try:
                            zip_response = requests.get(
                                f"http://localhost:5010/download_article_zip/{article['article_id']}",
                                timeout=60
                            )
                            if zip_response.status_code == 200:
                                zip_size = len(zip_response.content)
                                print(f"   ✅ ZIP generated: {zip_size} bytes")
                                
                                # Save ZIP file for inspection
                                zip_filename = f"guy_raz_article_{article['article_id']}.zip"
                                with open(zip_filename, 'wb') as f:
                                    f.write(zip_response.content)
                                print(f"   📁 Saved: {zip_filename}")
                            else:
                                print(f"   ❌ ZIP failed: HTTP {zip_response.status_code}")
                        except Exception as e:
                            print(f"   ❌ ZIP error: {e}")
                        print()
                
            return result
        else:
            print(f"Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"Request failed: {e}")
        return None

if __name__ == "__main__":
    result = test_guy_raz_newsletter()
    if result and result.get('status') == 'success':
        print("✅ TEST PASSED: Guy Raz newsletter processed successfully")
    else:
        print("❌ TEST FAILED: Newsletter processing failed")