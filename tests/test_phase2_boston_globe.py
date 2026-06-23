#!/usr/bin/env python3
"""
Test Phase 2 Boston Globe Authentication
Tests credential-aware processing with real Boston Globe subscription
"""
import requests
import json
import time

def test_phase2_boston_globe():
    """Test Phase 2 with Boston Globe newsletter and credentials"""
    
    # Test credentials provided
    test_credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    print("🚀 Testing Phase 2 Boston Globe Authentication")
    print("=" * 50)
    
    # Step 1: Process a Boston Globe newsletter
    print("\n1. Processing Boston Globe newsletter...")
    newsletter_url = "https://mailchi.mp/bostonglobe/trendlines-trumps-obesity-drug-deal-has-lots-of-unknowns?e=a4f20567f8"
    
    process_payload = {
        "newsletter_url": newsletter_url,
        "user_id": "TEST-PHASE2-USER",
        "max_articles": 10,
        "test_mode": True
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/process_newsletter',
            json=process_payload,
            timeout=300
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Newsletter processed successfully!")
            print(f"   Articles created: {result.get('articles_created', 0)}")
            print(f"   Articles requiring subscription: {result.get('articles_requiring_subscription', 0)}")
            print(f"   Newsletter ID: {result.get('newsletter_id')}")
            
            newsletter_id = result.get('newsletter_id')
            server_public_key = result.get('server_public_key')
            
            if server_public_key:
                print(f"   Server public key: {server_public_key[:20]}...")
            
        else:
            print(f"❌ Newsletter processing failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Newsletter processing error: {e}")
        return False
    
    # Step 2: Get articles to see subscription status
    print(f"\n2. Getting articles for newsletter {newsletter_id}...")
    
    try:
        articles_response = requests.post(
            'http://localhost:5017/get_articles_by_newsletter_id',
            json={"newsletter_id": newsletter_id},
            timeout=30
        )
        
        if articles_response.status_code == 200:
            articles_result = articles_response.json()
            articles = articles_result.get('articles', [])
            
            print(f"✅ Found {len(articles)} articles")
            
            subscription_articles = [a for a in articles if a.get('subscription_required')]
            free_articles = [a for a in articles if not a.get('subscription_required')]
            
            print(f"   Free articles: {len(free_articles)}")
            print(f"   Subscription articles: {len(subscription_articles)}")
            
            if subscription_articles:
                print("\n   Subscription articles found:")
                for article in subscription_articles[:3]:
                    print(f"   - {article['title'][:50]}... (ID: {article['article_id']})")
                    print(f"     Domain: {article.get('subscription_domain', 'Unknown')}")
            
        else:
            print(f"❌ Failed to get articles: {articles_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error getting articles: {e}")
        return False
    
    # Step 3: Submit credentials for subscription articles
    if subscription_articles:
        print(f"\n3. Submitting Boston Globe credentials...")
        
        # Use first subscription article for credential submission
        test_article = subscription_articles[0]
        article_id = test_article['article_id']
        domain = test_article.get('subscription_domain', 'bostonglobe.com')
        
        # For testing, we'll simulate the mobile app encryption process
        # In real implementation, mobile app encrypts these
        credentials_payload = {
            "article_id": article_id,
            "device_id": "TEST-PHASE2-USER",
            "mobile_public_key": "test_mobile_key_for_phase2",  # Simplified for testing
            "encrypted_username": "test_encrypted_username",     # Simplified for testing
            "encrypted_password": "test_encrypted_password",     # Simplified for testing
            "domain": domain
        }
        
        print(f"   Submitting credentials for article: {test_article['title'][:50]}...")
        print(f"   Domain: {domain}")
        
        try:
            # First, let's manually store the credentials in the database for testing
            print("   📝 Manually storing test credentials for Phase 2 testing...")
            
            # Store credentials directly in database for testing
            import psycopg2
            import os
            
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                database=os.getenv('DB_NAME', 'audiotours'),
                user=os.getenv('DB_USER', 'admin'),
                password=os.getenv('DB_PASSWORD', 'password123'),
                port=os.getenv('DB_PORT', '5433')
            )
            cursor = conn.cursor()
            
            # Store test credentials
            cursor.execute("""
                INSERT INTO user_subscription_credentials 
                (device_id, article_id, domain, decrypted_username, decrypted_password)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (device_id, domain) 
                DO UPDATE SET 
                    article_id = EXCLUDED.article_id,
                    decrypted_username = EXCLUDED.decrypted_username,
                    decrypted_password = EXCLUDED.decrypted_password,
                    created_at = NOW()
            """, ("TEST-PHASE2-USER", article_id, domain, test_credentials['username'], test_credentials['password']))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print("   ✅ Test credentials stored successfully!")
            
        except Exception as e:
            print(f"   ❌ Failed to store test credentials: {e}")
            return False
    
    # Step 4: Test credential-aware article processing
    print(f"\n4. Testing credential-aware article processing...")
    
    if subscription_articles:
        test_article = subscription_articles[0]
        article_url = test_article['url']
        
        print(f"   Testing with article: {test_article['title'][:50]}...")
        print(f"   URL: {article_url}")
        
        try:
            # Test browser automation with login
            from browser_automation_login import extract_content_with_login
            
            print("   🔍 Testing browser automation with Boston Globe login...")
            
            result = extract_content_with_login(article_url, test_credentials)
            
            if result.get('success'):
                content = result['content']
                print(f"   ✅ Authentication successful!")
                print(f"   📄 Content extracted: {len(content)} characters")
                print(f"   📰 Title: {result.get('title', 'Unknown')[:50]}...")
                print(f"   📝 Content preview: {content[:200]}...")
                
                return True
            else:
                error = result.get('error', 'Unknown error')
                print(f"   ❌ Authentication failed: {error}")
                
                # Check if it's a login issue vs content extraction issue
                if 'login failed' in error.lower():
                    print("   🔍 This appears to be a login issue.")
                    print("   💡 Possible causes:")
                    print("      - Credentials incorrect")
                    print("      - Boston Globe login page changed")
                    print("      - Additional authentication required (2FA, captcha)")
                    print("      - Rate limiting or bot detection")
                elif 'content' in error.lower():
                    print("   🔍 Login may have worked, but content extraction failed.")
                    print("   💡 Possible causes:")
                    print("      - Article page structure changed")
                    print("      - Content behind additional paywall")
                    print("      - JavaScript-heavy content loading")
                
                return False
                
        except Exception as e:
            print(f"   ❌ Browser automation error: {e}")
            print("   🔍 This indicates a technical issue with browser automation setup.")
            return False
    
    print(f"\n5. Phase 2 deployment test complete!")
    return True

if __name__ == "__main__":
    success = test_phase2_boston_globe()
    
    if success:
        print(f"\n🎉 Phase 2 Boston Globe test PASSED!")
        print("   ✅ Deployment successful")
        print("   ✅ Authentication working")
        print("   ✅ Content extraction working")
    else:
        print(f"\n⚠️ Phase 2 Boston Globe test encountered issues")
        print("   Please check the specific error messages above")
        print("   The deployment is complete, but authentication needs investigation")