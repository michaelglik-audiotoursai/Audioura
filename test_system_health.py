#!/usr/bin/env python3
"""
AudioTours System Health Check
Tests core functionality and service availability
"""
import requests
import json
import psycopg2
from datetime import datetime

def test_service_health():
    """Test all service endpoints for basic health"""
    print("=== SERVICE HEALTH CHECK ===")
    
    services = [
        ("Newsletter Processor", "http://localhost:5017/health", "GET"),
        ("News Orchestrator", "http://localhost:5012/health", "GET"),
        ("News Generator", "http://localhost:5010/health", "GET"),
        ("News Processor", "http://localhost:5011/health", "GET"),
        ("Polly TTS", "http://localhost:5018/health", "GET"),
        ("Tour Orchestrator", "http://localhost:5002/health", "GET"),
        ("Tour Processor", "http://localhost:5001/health", "GET"),
        ("Map Delivery", "http://localhost:5005/health", "GET"),
        ("Coordinates", "http://localhost:5006/health", "GET"),
        ("Treats", "http://localhost:5007/health", "GET"),
    ]
    
    results = []
    for name, url, method in services:
        try:
            if method == "GET":
                response = requests.get(url, timeout=5)
            else:
                response = requests.post(url, timeout=5)
            
            status = "ONLINE" if response.status_code in [200, 404] else f"ERROR {response.status_code}"
            results.append((name, status, response.status_code))
            print(f"  {name}: {status}")
            
        except Exception as e:
            results.append((name, "OFFLINE", str(e)))
            print(f"  {name}: OFFLINE ({str(e)[:50]})")
    
    return results

def test_database_connectivity():
    """Test database connection and basic queries"""
    print("\n=== DATABASE CONNECTIVITY ===")
    
    try:
        conn = psycopg2.connect(
            host='localhost', database='audiotours', user='admin', 
            password='password123', port='5433'
        )
        cursor = conn.cursor()
        
        # Test basic queries
        cursor.execute("SELECT COUNT(*) FROM newsletters")
        newsletter_count = cursor.fetchone()[0]
        print(f"  Newsletters: {newsletter_count} records")
        
        cursor.execute("SELECT COUNT(*) FROM article_requests")
        article_count = cursor.fetchone()[0]
        print(f"  Articles: {article_count} records")
        
        cursor.execute("SELECT COUNT(*) FROM audio_tours")
        tour_count = cursor.fetchone()[0]
        print(f"  Tours: {tour_count} records")
        
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"  Users: {user_count} records")
        
        # Test recent activity
        cursor.execute("""
            SELECT COUNT(*) FROM article_requests 
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
        recent_articles = cursor.fetchone()[0]
        print(f"  Recent articles (24h): {recent_articles}")
        
        cursor.close()
        conn.close()
        print("  Database: CONNECTED")
        return True
        
    except Exception as e:
        print(f"  Database: ERROR - {e}")
        return False

def test_audio_generation():
    """Test audio generation pipeline"""
    print("\n=== AUDIO GENERATION TEST ===")
    
    try:
        # Test Polly TTS directly
        payload = {
            "text": "This is a test of the audio generation system.",
            "voice": "Joanna"
        }
        
        response = requests.post(
            "http://localhost:5018/synthesize",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            audio_size = len(response.content)
            print(f"  Polly TTS: SUCCESS ({audio_size} bytes)")
            return True
        else:
            print(f"  Polly TTS: FAILED (HTTP {response.status_code})")
            return False
            
    except Exception as e:
        print(f"  Polly TTS: ERROR - {e}")
        return False

def test_recent_articles():
    """Check recent article processing results"""
    print("\n=== RECENT ARTICLE ANALYSIS ===")
    
    try:
        conn = psycopg2.connect(
            host='localhost', database='audiotours', user='admin', 
            password='password123', port='5433'
        )
        cursor = conn.cursor()
        
        # Get recent finished articles
        cursor.execute("""
            SELECT article_id, request_string, status, 
                   LENGTH(article_text) as content_length,
                   finished_at
            FROM article_requests 
            WHERE finished_at > NOW() - INTERVAL '2 hours'
            AND status = 'finished'
            ORDER BY finished_at DESC 
            LIMIT 5
        """)
        
        articles = cursor.fetchall()
        
        if articles:
            print(f"  Recent finished articles: {len(articles)}")
            for i, (article_id, title, status, length, finished_at) in enumerate(articles, 1):
                print(f"    {i}. {title[:40]}...")
                print(f"       ID: {article_id}")
                print(f"       Content: {length} chars")
                print(f"       Finished: {finished_at}")
                print(f"       ZIP: curl -X GET \"http://localhost:5012/download/{article_id}\" -o \"recent_{i}.zip\"")
        else:
            print("  No recent finished articles found")
        
        # Check for failed articles
        cursor.execute("""
            SELECT COUNT(*) FROM article_requests 
            WHERE created_at > NOW() - INTERVAL '2 hours'
            AND status = 'failed'
        """)
        failed_count = cursor.fetchone()[0]
        
        if failed_count > 0:
            print(f"  WARNING: {failed_count} failed articles in last 2 hours")
        else:
            print("  No failed articles in last 2 hours")
        
        cursor.close()
        conn.close()
        return len(articles) > 0
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_newsletter_pattern_recognition():
    """Test pattern recognition capabilities"""
    print("\n=== PATTERN RECOGNITION TEST ===")
    
    try:
        # Test with a simple newsletter URL (not daily limited)
        test_url = "https://example.substack.com/p/test-newsletter"
        
        payload = {
            "newsletter_url": test_url,
            "user_id": "test_user_newsletter",
            "max_articles": 3,
            "test_mode": True  # If supported
        }
        
        response = requests.post(
            "http://localhost:5017/process_newsletter",
            json=payload,
            timeout=60
        )
        
        print(f"  Newsletter processor response: HTTP {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"  Pattern recognition: WORKING")
            return True
        elif response.status_code == 400:
            error_data = response.json()
            if "daily_limit_reached" in error_data.get("error_type", ""):
                print(f"  Pattern recognition: WORKING (daily limit protection active)")
                return True
            else:
                print(f"  Pattern recognition: ERROR - {error_data.get('message', 'Unknown')}")
                return False
        else:
            print(f"  Pattern recognition: ERROR - HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  Pattern recognition: ERROR - {e}")
        return False

def main():
    """Run comprehensive system health check"""
    print("AUDIOTOURS SYSTEM HEALTH CHECK")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")
    
    # Run all tests
    service_results = test_service_health()
    db_connected = test_database_connectivity()
    audio_working = test_audio_generation()
    recent_articles = test_recent_articles()
    pattern_recognition = test_newsletter_pattern_recognition()
    
    # Generate summary
    print(f"\n{'='*60}")
    print("SYSTEM HEALTH SUMMARY")
    print(f"{'='*60}")
    
    # Service status
    online_services = sum(1 for _, status, _ in service_results if status == "ONLINE")
    total_services = len(service_results)
    print(f"Services Online: {online_services}/{total_services}")
    
    # Component status
    components = [
        ("Database", db_connected),
        ("Audio Generation", audio_working),
        ("Recent Processing", recent_articles),
        ("Pattern Recognition", pattern_recognition)
    ]
    
    working_components = sum(1 for _, working in components if working)
    total_components = len(components)
    
    print(f"Components Working: {working_components}/{total_components}")
    
    for name, working in components:
        status = "WORKING" if working else "FAILED"
        print(f"  {name}: {status}")
    
    # Overall health
    overall_health = (online_services / total_services + working_components / total_components) / 2
    print(f"\nOverall System Health: {overall_health*100:.1f}%")
    
    if overall_health >= 0.8:
        print("Status: HEALTHY - System ready for production use")
    elif overall_health >= 0.6:
        print("Status: DEGRADED - Some components need attention")
    else:
        print("Status: CRITICAL - Multiple system failures detected")
    
    # Save detailed results
    report = {
        'timestamp': datetime.now().isoformat(),
        'services': [{'name': name, 'status': status, 'code': code} for name, status, code in service_results],
        'components': [{'name': name, 'working': working} for name, working in components],
        'overall_health': overall_health,
        'summary': {
            'services_online': online_services,
            'total_services': total_services,
            'components_working': working_components,
            'total_components': total_components
        }
    }
    
    report_file = f"system_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_file}")
    
    # Return failure count for exit code
    failures = (total_services - online_services) + (total_components - working_components)
    return failures

if __name__ == "__main__":
    failures = main()
    exit(failures)