#!/usr/bin/env python3
"""
Newsletter Cloud Test Suite
============================
Tests newsletter processing end-to-end through the cloud gateway (api.audioura.com).
Also works locally by changing BASE_URL.

Usage:
    # Cloud (default):
    python test_newsletter_cloud.py

    # Local:
    python test_newsletter_cloud.py --local

    # Custom API key:
    set GATEWAY_API_KEY=your-key
    python test_newsletter_cloud.py

Requires: requests (pip install requests)
"""
import os
import sys
import json
import time
import requests
import argparse
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CLOUD_URL = "https://api.audioura.com"
LOCAL_URL = "http://localhost:5017"

# API key from environment or .env file (required for cloud cost-bearing endpoints)
# Load from .env if present (keeps secrets out of source control)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment

API_KEY = os.getenv('GATEWAY_API_KEY', '')

# Test newsletters — mix of technologies
TEST_CASES = [
    {
        "url": "https://mailchi.mp/cb820171cc62/newton-has-decided-election-night-2025-results?e=f2ed12d013",
        "name": "MailChimp Newton",
        "expected_min_articles": 3,
    },
    {
        "url": "https://guyraz.substack.com/p/the-7-lessons-behind-gymsharks-billion?utm_source=post-email-title&publication_id=2607539&post_id=179214153&utm_campaign=email-post-title&isFreemail=true&r=4ldjqb&triedRedirect=true&utm_medium=email",
        "name": "Guy Raz Substack",
        "expected_min_articles": 3,
    },
]


def make_headers(api_key_required=False):
    headers = {'Content-Type': 'application/json'}
    if api_key_required and API_KEY:
        headers['X-API-Key'] = API_KEY
    return headers


def test_health(base_url):
    """Verify gateway/service is reachable."""
    print("\n--- Health Check ---")
    try:
        r = requests.get(f"{base_url}/health", timeout=10)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            print(f"  Response: {r.json()}")
            return True
        return False
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_newsletters_list(base_url):
    """GET /newsletters_v2 — list existing newsletters."""
    print("\n--- List Newsletters ---")
    # Cloud uses /newsletters_v2, local uses same path
    url = f"{base_url}/newsletters_v2"
    try:
        r = requests.get(url, headers=make_headers(), timeout=15)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            newsletters = data.get('newsletters', [])
            print(f"  Found {len(newsletters)} newsletter(s)")
            for nl in newsletters[:5]:
                print(f"    - {nl.get('title', nl.get('newsletter_url', '?'))[:60]}")
            return True
        else:
            print(f"  Error: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_process_newsletter(base_url, newsletter_url, name, is_cloud=True):
    """POST /process_newsletter — submit a newsletter for processing."""
    print(f"\n--- Process Newsletter: {name} ---")
    print(f"  URL: {newsletter_url[:80]}...")

    endpoint = f"{base_url}/process_newsletter"
    payload = {
        "newsletter_url": newsletter_url,
        "user_id": "cloud_test_user",
        "max_articles": 5,
        "test_mode": True,
    }

    try:
        r = requests.post(endpoint, json=payload, headers=make_headers(api_key_required=True), timeout=180)
        print(f"  Status: {r.status_code}")

        if r.status_code == 200:
            result = r.json()
            articles = result.get('articles_created', 0)
            newsletter_id = result.get('newsletter_id', 'N/A')
            print(f"  ✅ SUCCESS: {articles} articles created (newsletter_id={newsletter_id})")
            return result
        elif r.status_code == 401:
            print(f"  ❌ AUTH ERROR: API key required. Set GATEWAY_API_KEY env var.")
            return None
        elif r.status_code == 503:
            print(f"  ❌ SERVICE ERROR: {r.json().get('message', r.text[:200])}")
            return None
        else:
            print(f"  ❌ HTTP {r.status_code}: {r.text[:300]}")
            return None
    except requests.Timeout:
        print(f"  ❌ TIMEOUT (180s) — newsletter may still be processing")
        return None
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return None


def test_get_articles(base_url, newsletter_id, is_cloud=True):
    """POST /get_articles_by_newsletter_id — get articles for a newsletter."""
    print(f"\n--- Get Articles for newsletter {newsletter_id} ---")

    endpoint = f"{base_url}/get_articles_by_newsletter_id"
    payload = {"newsletter_id": newsletter_id}

    try:
        r = requests.post(endpoint, json=payload, headers=make_headers(), timeout=15)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            articles = data.get('articles', [])
            print(f"  Found {len(articles)} article(s)")
            for art in articles[:5]:
                title = art.get('title', art.get('request_string', '?'))
                status = art.get('status', '?')
                print(f"    - [{status}] {title[:60]}")
            return articles
        else:
            print(f"  Error: {r.text[:200]}")
            return []
    except Exception as e:
        print(f"  FAILED: {e}")
        return []


def test_download_article(base_url, article_id, is_cloud=True):
    """GET /news-download/<id> — download a processed article ZIP."""
    print(f"\n--- Download Article {article_id} ---")

    if is_cloud:
        endpoint = f"{base_url}/news-download/{article_id}"
    else:
        endpoint = f"{base_url}/download/{article_id}"

    try:
        r = requests.get(endpoint, headers=make_headers(), timeout=30)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            content_type = r.headers.get('content-type', '')
            size = len(r.content)
            print(f"  ✅ Downloaded: {size} bytes ({content_type})")
            return True
        else:
            print(f"  ❌ Error: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Newsletter Cloud Test Suite")
    parser.add_argument('--local', action='store_true', help='Test against local Docker (localhost:5017)')
    parser.add_argument('--url', type=str, help='Custom base URL')
    parser.add_argument('--quick', action='store_true', help='Only test health + list (no processing)')
    args = parser.parse_args()

    if args.url:
        base_url = args.url
        is_cloud = 'audioura.com' in base_url
    elif args.local:
        base_url = LOCAL_URL
        is_cloud = False
    else:
        base_url = CLOUD_URL
        is_cloud = True

    print("=" * 70)
    print("AUDIOURA NEWSLETTER CLOUD TEST SUITE")
    print("=" * 70)
    print(f"Target:   {base_url}")
    print(f"Mode:     {'CLOUD' if is_cloud else 'LOCAL'}")
    print(f"API Key:  {'SET' if API_KEY else 'NOT SET (cost-bearing endpoints will fail)'}")
    print(f"Time:     {datetime.now().isoformat()}")
    print("=" * 70)

    # 1. Health check
    if not test_health(base_url):
        print("\n❌ ABORTED: Service unreachable")
        sys.exit(1)

    # 2. List newsletters
    test_newsletters_list(base_url)

    if args.quick:
        print("\n[--quick] Skipping processing tests.")
        return

    # 3. Process each test newsletter
    if not API_KEY and is_cloud:
        print("\n⚠️  GATEWAY_API_KEY not set — skipping process tests (requires API key on cloud)")
        print("   Set it with: set GATEWAY_API_KEY=your-key-here")
        return

    results = []
    for tc in TEST_CASES:
        result = test_process_newsletter(base_url, tc['url'], tc['name'], is_cloud)
        if result:
            newsletter_id = result.get('newsletter_id')
            if newsletter_id:
                # Get articles
                articles = test_get_articles(base_url, newsletter_id, is_cloud)
                # Try downloading first finished article
                for art in articles:
                    if art.get('status') == 'finished':
                        test_download_article(base_url, art.get('article_id'), is_cloud)
                        break
            results.append({"name": tc['name'], "success": True, "articles": result.get('articles_created', 0)})
        else:
            results.append({"name": tc['name'], "success": False, "articles": 0})

        time.sleep(2)  # Brief pause between tests

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r['success'])
    total = len(results)
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"  {status} {r['name']}: {r['articles']} articles")
    print(f"\n  {passed}/{total} passed")
    print("=" * 70)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
