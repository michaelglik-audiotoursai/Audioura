#!/usr/bin/env python3
"""
NY Times Newsletter Test Program
Tests NY Times newsletter processing with subscription credentials
"""
import requests
import json
import psycopg2
from datetime import datetime

def cleanup_nytimes_newsletter():
    """Clean up any existing NY Times newsletter records"""
    try:
        conn = psycopg2.connect(
            host='localhost', database='audiotours', user='admin', 
            password='password123', port='5433'
        )
        cursor = conn.cursor()
        
        # Clean up NY Times newsletters
        cursor.execute("DELETE FROM newsletters WHERE url LIKE '%nytimes.com%'")
        deleted = cursor.rowcount
        
        conn.commit()
        print(f"Cleaned up {deleted} NY Times newsletter records")
        
    except Exception as e:
        print(f"Cleanup error: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def test_nytimes_newsletter():
    """Test NY Times newsletter processing"""
    newsletter_url = "https://nl.nytimes.com/f/a/U1pikD1QtR3tGYamysXC2Q~~/AAAAARA~/-8uIGU8r2JbBucijsG_B2mMYtFPB1bVYjJ2GDx0U6XnmPbA1BOf2XfTZO8qDtcAaO3wTn5H2-_SY0IrJ38od4-X26ZZgdDZY6PPd1BmRlb_k23PSwGIM4pUCVJakVaWFa1FIDTcpLUHZVPRNWJ3L_tUgSEiJTtkHbV9A86NTP_PEc6PyXBwBVj2B36mF327c-w_UC3-7pL63ofzV5khb9WDz3ME5LMyzKpBHAwlEz6PX2ZBvYDfVOEZ-jf780_tPCPqEkz95kIUgqYoRy231aNBrWc8Y_Ox9NpwV9_vSC9S_L-6fzaDDf8i1P1534GVshe8iO_HEoeRUYzuU5XpHsCX1GmyQLrl-z8eCyywz6oNKki4Z7RTJG4MoYaDAzFHF8VsrPnO1g39_5TzBaOAdirqulKG7S6UAgNtSUXS-Cs28tYCAROiXsNLT7K7SCwropjCLK4dBQxstcNgFMwU8o7GJUoXeWMm5hvGeHQPsLzGaZvaWvHwIiNjGY5DJsJ4YykwkoUyPa006fA_v-wnikaSH_HJdc0gyez6jER0GyE8~"
    
    print("NY TIMES NEWSLETTER TEST")
    print("=" * 60)
    print(f"URL: {newsletter_url}")
    print(f"Started at: {datetime.now()}")
    
    # Step 1: Cleanup
    print("\n=== STEP 1: Database Cleanup ===")
    cleanup_nytimes_newsletter()
    
    # Step 2: Process Newsletter
    print("\n=== STEP 2: Newsletter Processing ===")
    try:
        payload = {
            "newsletter_url": newsletter_url,
            "user_id": "USER-281301397",
            "max_articles": 10,
            "test_mode": True
        }
        
        print("Sending request to newsletter processor...")
        response = requests.post(
            "http://localhost:5017/process_newsletter",
            json=payload,
            timeout=300  # 5 minutes for NY Times
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"SUCCESS: Newsletter processed")
            print(f"Newsletter ID: {result.get('newsletter_id', 'N/A')}")
            print(f"Articles created: {result.get('articles_created', 0)}")
            print(f"Articles requiring subscription: {result.get('articles_requiring_subscription', 0)}")
            
            # Save response
            with open('nytimes_newsletter_response.json', 'w') as f:
                json.dump(result, f, indent=2)
            print("Response saved to: nytimes_newsletter_response.json")
            
            return result
        else:
            print(f"FAILED: HTTP {response.status_code}")
            print(f"Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"ERROR: Newsletter processing failed: {e}")
        return None

def submit_nytimes_credentials(newsletter_id, article_id):
    """Submit NY Times credentials for subscription articles"""
    print("\n=== STEP 3: Submit Credentials ===")
    
    credentials_payload = {
        "article_id": article_id,
        "device_id": "USER-281301397", 
        "newsletter_id": newsletter_id,
        "encrypted_username": "glikfamily@gmail.com",  # Will be encrypted by mobile app
        "encrypted_password": "Eight6Nine8",  # Will be encrypted by mobile app
        "domain": "nytimes.com"
    }
    
    try:
        response = requests.post(
            "http://localhost:5017/submit_credentials",
            json=credentials_payload,
            timeout=60
        )
        
        print(f"Credentials response: {response.status_code}")
        if response.status_code == 200:
            print("SUCCESS: Credentials submitted")
            return True
        else:
            print(f"FAILED: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR: Credential submission failed: {e}")
        return False

def verify_nytimes_articles(newsletter_id):
    """Verify NY Times articles were created"""
    print("\n=== STEP 4: Database Verification ===")
    try:
        conn = psycopg2.connect(
            host='localhost', database='audiotours', user='admin', 
            password='password123', port='5433'
        )
        cursor = conn.cursor()
        
        # Get articles
        cursor.execute("""
            SELECT ar.article_id, ar.request_string, ar.status, 
                   LENGTH(ar.article_text) as content_length,
                   ar.subscription_required, ar.subscription_domain
            FROM article_requests ar
            JOIN newsletters_article_link nar ON ar.article_id = nar.article_requests_id
            WHERE nar.newsletters_id = %s
            ORDER BY ar.created_at DESC
        """, (newsletter_id,))
        
        articles = cursor.fetchall()
        print(f"Found {len(articles)} articles")
        
        subscription_articles = 0
        for i, (article_id, title, status, length, sub_required, sub_domain) in enumerate(articles, 1):
            print(f"\n  {i}. {title[:50]}...")
            print(f"     ID: {article_id}")
            print(f"     Status: {status}")
            print(f"     Content: {length} chars")
            print(f"     Subscription Required: {sub_required}")
            print(f"     Domain: {sub_domain}")
            
            if sub_required:
                subscription_articles += 1
                print(f"     🔒 SUBSCRIPTION ARTICLE - Credentials needed")
            
            if status == 'finished' and length > 100:
                print(f"     ZIP: curl -X GET \"http://localhost:5012/download/{article_id}\" -o \"nytimes_{i}.zip\"")
        
        print(f"\nSummary:")
        print(f"Total articles: {len(articles)}")
        print(f"Subscription articles: {subscription_articles}")
        print(f"Free articles: {len(articles) - subscription_articles}")
        
        return articles
        
    except Exception as e:
        print(f"ERROR: Database verification failed: {e}")
        return []
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def main():
    """Run NY Times newsletter test"""
    # Process newsletter
    result = test_nytimes_newsletter()
    
    if result and result.get('newsletter_id'):
        newsletter_id = result['newsletter_id']
        
        # Verify articles
        articles = verify_nytimes_articles(newsletter_id)
        
        # Submit credentials for subscription articles
        subscription_articles = [a for a in articles if a[4]]  # subscription_required = True
        if subscription_articles:
            print(f"\n=== CREDENTIAL SUBMISSION TEST ===")
            print(f"Found {len(subscription_articles)} subscription articles")
            
            # Test with first subscription article
            first_sub_article = subscription_articles[0]
            article_id = first_sub_article[0]
            
            print(f"Testing credentials with article: {article_id}")
            submit_nytimes_credentials(newsletter_id, article_id)
        
        print(f"\n=== NY TIMES TEST COMPLETE ===")
        print(f"Newsletter ID: {newsletter_id}")
        print(f"Total articles: {len(articles)}")
        print(f"Subscription articles: {len(subscription_articles)}")
        
    else:
        print("NY Times newsletter test failed")

if __name__ == "__main__":
    main()