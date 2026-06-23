#!/usr/bin/env python3
"""
Comprehensive test suite for all newsletter technologies
Tests: MailChimp, Apple Podcasts, Spotify, Quora, and Guy Raz (Substack)
"""
import requests
import json
import time

def test_newsletter_technology(name, url, expected_articles_min=1):
    """Test a specific newsletter technology"""
    print(f"\n=== Testing {name} ===")
    print(f"URL: {url}")
    
    payload = {
        "newsletter_url": url,
        "user_id": "test_user",
        "max_articles": 10
    }
    
    try:
        response = requests.post(
            "http://localhost:5017/process_newsletter",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            articles_created = result.get('articles_created', 0)
            articles_failed = result.get('articles_failed', 0)
            
            print(f"✅ SUCCESS: {articles_created} articles created, {articles_failed} failed")
            
            if articles_created >= expected_articles_min:
                print(f"✅ PASS: Met minimum requirement ({expected_articles_min}+ articles)")
                return True, articles_created
            else:
                print(f"❌ FAIL: Below minimum requirement ({articles_created} < {expected_articles_min})")
                return False, articles_created
        else:
            error_data = response.json() if response.headers.get('content-type') == 'application/json' else response.text
            print(f"❌ FAIL: HTTP {response.status_code}")
            print(f"Error: {error_data}")
            return False, 0
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False, 0

def cleanup_newsletter(url):
    """Clean up newsletter for retesting"""
    try:
        import subprocess
        result = subprocess.run([
            "python", "cleanup_newsletter_simple.py", "--url", url
        ], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"🧹 Cleaned up: {url}")
        else:
            print(f"⚠️ Cleanup failed: {result.stderr}")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

def main():
    """Run comprehensive newsletter technology tests"""
    print("🧪 COMPREHENSIVE NEWSLETTER TECHNOLOGY TEST SUITE")
    print("=" * 60)
    
    # Test cases: (name, url, min_expected_articles)
    test_cases = [
        # MailChimp newsletters
        ("MailChimp Newsletter", 
         "https://mailchi.mp/example/newsletter", 
         1),
        
        # Apple Podcasts (from working tests)
        ("Apple Podcasts Episode",
         "https://podcasts.apple.com/us/podcast/how-i-built-this-with-guy-raz/id1150510297?i=1000634123456",
         1),
        
        # Spotify Episodes (from working tests) 
        ("Spotify Episode",
         "https://open.spotify.com/episode/3kFbvWAO7PzT4XC7bpUF9y",
         1),
        
        # Quora newsletters (from working tests)
        ("Quora Newsletter",
         "https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717",
         1),
        
        # Guy Raz Substack (the problematic one)
        ("Guy Raz Substack",
         "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539",
         1)
    ]
    
    results = []
    
    for name, url, min_expected in test_cases:
        # Clean up first
        cleanup_newsletter(url)
        time.sleep(2)  # Brief pause between cleanup and test
        
        # Run test
        success, articles_count = test_newsletter_technology(name, url, min_expected)
        results.append({
            'name': name,
            'success': success,
            'articles': articles_count,
            'url': url
        })
        
        time.sleep(3)  # Pause between tests
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for result in results:
        status = "✅ PASS" if result['success'] else "❌ FAIL"
        print(f"{status} {result['name']}: {result['articles']} articles")
        if result['success']:
            passed += 1
        else:
            failed += 1
    
    print(f"\nOverall: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED - Safe to implement browser automation by default")
    else:
        print("⚠️ SOME TESTS FAILED - Review failures before implementing browser automation")
    
    return failed == 0

if __name__ == "__main__":
    main()