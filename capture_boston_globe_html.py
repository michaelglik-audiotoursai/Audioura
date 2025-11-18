#!/usr/bin/env python3
"""
Simple Boston Globe HTML Capture
Captures initial HTML pages for analysis without browser automation
"""
import requests
import time
import os

def capture_boston_globe_pages():
    """Capture Boston Globe login and related pages"""
    
    # Create directory for HTML files
    html_dir = "boston_globe_html_analysis"
    if not os.path.exists(html_dir):
        os.makedirs(html_dir)
    
    # Enhanced headers to mimic real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none'
    }
    
    urls_to_capture = [
        ('login_page', 'https://www.bostonglobe.com/login'),
        ('homepage', 'https://www.bostonglobe.com/'),
        ('subscribe_page', 'https://www.bostonglobe.com/subscribe'),
        ('sample_article', 'https://www.bostonglobe.com/2024/11/13/business/')
    ]
    
    session = requests.Session()
    session.headers.update(headers)
    
    print("🔍 CAPTURING BOSTON GLOBE HTML PAGES")
    print("=" * 50)
    
    for name, url in urls_to_capture:
        try:
            print(f"\n📄 Capturing: {name}")
            print(f"   URL: {url}")
            
            response = session.get(url, timeout=30)
            
            print(f"   Status: {response.status_code}")
            print(f"   Content Length: {len(response.text)} chars")
            
            # Save HTML file
            timestamp = time.strftime("%H%M%S")
            filename = f"{timestamp}_{name}.html"
            filepath = os.path.join(html_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Captured: {time.strftime('%Y-%m-%d %H:%M:%S')} -->\n")
                f.write(f"<!-- URL: {url} -->\n")
                f.write(f"<!-- Status: {response.status_code} -->\n")
                f.write(f"<!-- Content-Length: {len(response.text)} -->\n")
                f.write(response.text)
            
            print(f"   ✅ Saved: {filepath}")
            
            # Analyze content briefly
            content_lower = response.text.lower()
            login_indicators = []
            if 'email' in content_lower:
                login_indicators.append('email')
            if 'password' in content_lower:
                login_indicators.append('password')
            if 'sign in' in content_lower:
                login_indicators.append('sign in')
            if 'tinypass' in content_lower:
                login_indicators.append('tinypass')
            if 'auth.bostonglobe' in content_lower:
                login_indicators.append('auth.bostonglobe')
                
            if login_indicators:
                print(f"   🔍 Login indicators: {', '.join(login_indicators)}")
            
        except Exception as e:
            print(f"   ❌ Failed to capture {name}: {e}")
            
        time.sleep(2)  # Be respectful
    
    print(f"\n✅ HTML capture complete!")
    print(f"📁 Files saved to: {os.path.abspath(html_dir)}")
    
    return html_dir

if __name__ == "__main__":
    capture_boston_globe_pages()