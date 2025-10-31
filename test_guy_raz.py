#!/usr/bin/env python3
"""
Test Guy Raz newsletter processing with fixed transaction handling
"""
import requests
import json

def test_guy_raz_newsletter():
    url = "http://localhost:5017/process_newsletter"
    
    payload = {
        "newsletter_url": "https://guyraz.substack.com/p/how-to-turn-a-small-struggling-business?utm_source=post-email-title&publication_id=2607539&post_id=177242273&utm_campaign=email-post-title&isFreemail=true&r=4ldjqb&triedRedirect=true&utm_medium=email",
        "user_id": "test_user",
        "max_articles": 10
    }
    
    print("Testing Guy Raz newsletter processing...")
    print(f"URL: {payload['newsletter_url']}")
    
    try:
        response = requests.post(url, json=payload, timeout=300)
        print(f"Status Code: {response.status_code}")
        
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        
        if result.get('status') == 'success':
            print(f"\n✅ SUCCESS!")
            print(f"Articles Found: {result.get('articles_found', 0)}")
            print(f"Articles Created: {result.get('articles_created', 0)}")
            print(f"Articles Failed: {result.get('articles_failed', 0)}")
            
            if result.get('failed_articles'):
                print(f"\nFailed Articles:")
                for i, failed in enumerate(result['failed_articles'][:3], 1):
                    print(f"  {i}. {failed.get('url', 'Unknown URL')}")
                    print(f"     Error: {failed.get('error', 'Unknown error')}")
        else:
            print(f"\n❌ FAILED: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ REQUEST FAILED: {e}")

if __name__ == "__main__":
    test_guy_raz_newsletter()