#!/usr/bin/env python3
"""
Test the URL matching fix
"""
import requests

def test_url_matching():
    """Test both working and problematic newsletters"""
    
    test_cases = [
        {
            'name': 'StockTwits (should work)',
            'url': 'https://thedailyrip.stocktwits.com/'
        },
        {
            'name': 'API Security issue-279 (was broken)',
            'url': 'https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/'
        },
        {
            'name': 'API Security issue-276 (was working)',
            'url': 'https://apisecurity.io/issue-276-api-discovery-hype-bola-at-mcdonalds-cisco-apis-exploited-input-validation-best-practices/'
        }
    ]
    
    print("=== TESTING URL MATCHING FIX ===\n")
    
    for test in test_cases:
        print(f"Testing: {test['name']}")
        print(f"URL: {test['url']}")
        
        try:
            response = requests.post(
                'http://localhost:5017/get_newsletter_articles',
                json={'newsletter_url': test['url']},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                articles = result.get('articles', [])
                print(f"✅ SUCCESS: Found {len(articles)} articles")
                if articles:
                    print(f"   First article: {articles[0]['title'][:50]}...")
            else:
                print(f"❌ FAILED: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
        
        print()

if __name__ == '__main__':
    test_url_matching()