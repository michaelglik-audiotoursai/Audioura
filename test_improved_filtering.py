#!/usr/bin/env python3
"""
Test the improved filtering with social media exclusion and content similarity
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import re
from datetime import datetime, timedelta

def clean_url(url):
    parsed = urlparse(url)
    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    return clean

def is_article_url(url):
    """Test the improved article URL detection"""
    # Social media exclusions
    exclude_patterns = [
        r'facebook\.com/sharer', r'twitter\.com/share', r'linkedin\.com/shareArticle',
        r't\.co/', r'bit\.ly/', r'tinyurl\.com/',
        r'\.jpg$', r'\.png$', r'\.pdf$', r'mailto:', r'tel:',
        r'/privacy', r'/terms', r'/contact', r'/advertise'
    ]
    
    for pattern in exclude_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            print(f"   ❌ EXCLUDED: {pattern}")
            return False
    
    # Article patterns
    article_patterns = [
        r'/news/', r'/blog/', r'/post/', r'/article/',
        r'/issue-', r'/report/', r'/analysis/',
        r'-\d{4}-', r'/\d{4}/', r'[a-z]+-[a-z]+-[a-z]+'
    ]
    
    for pattern in article_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            print(f"   ✅ MATCHES: {pattern}")
            return True
    
    return False

def test_improved_filtering():
    """Test the improved filtering logic"""
    print("=== TESTING IMPROVED FILTERING ===\n")
    
    test_urls = [
        "https://apisecurity.io/issue-280-solar-device-ato-attacks-smart-tvs-dumb-apis-password-reset-api-bugs-2025-developer-survey/",
        "https://apisecurity.io/issue-280-solar-device-ato-attacks-smart-tvs-dumb-apis-password-reset-api-bugs-2025-developer-survey/#content",
        "https://gbhackers.com/flowiseai-password-reset-token-vulnerability/",
        "https://survey.stackoverflow.co/2025/",
        "https://www.facebook.com/sharer/sharer.php?u=https://apisecurity.io/issue-280/",
        "https://twitter.com/share?url=Check%20out%20this%20article",
        "https://www.linkedin.com/shareArticle?mini=true&url=https://apisecurity.io/"
    ]
    
    for i, url in enumerate(test_urls, 1):
        print(f"{i}. Testing: {url}")
        if is_article_url(url):
            print(f"   RESULT: ✅ WOULD BE PROCESSED")
        else:
            print(f"   RESULT: ❌ WOULD BE EXCLUDED")
        print()

if __name__ == '__main__':
    test_improved_filtering()