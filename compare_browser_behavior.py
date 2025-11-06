#!/usr/bin/env python3
"""
Spotify Browser Comparison Analysis
Compare what we get vs what a real browser gets
"""
import sys
import os
sys.path.append('/app')

from browser_automation import get_browser
from selenium.webdriver.common.by import By
import time

def analyze_browser_differences(spotify_url):
    """Analyze differences between our browser automation and real browser"""
    browser = get_browser()
    
    if not browser.driver:
        print("❌ Browser not initialized")
        return
    
    try:
        print(f"🔍 Analyzing Spotify URL: {spotify_url}")
        print("=" * 60)
        
        # Get current user agent
        user_agent = browser.driver.execute_script("return navigator.userAgent;")
        print(f"🌐 Current User Agent: {user_agent}")
        
        # Get current browser settings
        window_size = browser.driver.get_window_size()
        print(f"📱 Window Size: {window_size}")
        
        # Load the page
        print(f"🔄 Loading page...")
        browser.driver.get(spotify_url)
        
        # Wait and check what we get
        time.sleep(5)
        
        # Get page info
        current_url = browser.driver.current_url
        page_title = browser.driver.title
        
        print(f"🔗 Final URL: {current_url}")
        print(f"📄 Page Title: {page_title}")
        
        # Check for redirects
        if current_url != spotify_url:
            print(f"⚠️  REDIRECT DETECTED!")
            print(f"   Original: {spotify_url}")
            print(f"   Final:    {current_url}")
        
        # Get page source info
        page_source = browser.driver.page_source
        print(f"📊 Page Source Length: {len(page_source)} characters")
        
        # Check for specific Spotify elements/messages
        spotify_indicators = [
            "Couldn't find that podcast",
            "Sign up to get unlimited",
            "Preview of Spotify",
            "Log in",
            "episode-title",
            "episode-description",
            "data-testid",
            "podcast-show"
        ]
        
        print("🔍 Content Analysis:")
        for indicator in spotify_indicators:
            if indicator in page_source:
                print(f"   ✅ Found: '{indicator}'")
            else:
                print(f"   ❌ Missing: '{indicator}'")
        
        # Check cookies
        cookies = browser.driver.get_cookies()
        print(f"🍪 Cookies: {len(cookies)} cookies set")
        for cookie in cookies[:3]:  # Show first 3 cookies
            print(f"   - {cookie['name']}: {cookie['value'][:20]}...")
        
        # Check JavaScript errors
        try:
            logs = browser.driver.get_log('browser')
            if logs:
                print(f"⚠️  Browser Console Errors: {len(logs)}")
                for log in logs[:3]:
                    print(f"   - {log['level']}: {log['message'][:100]}...")
            else:
                print("✅ No browser console errors")
        except:
            print("ℹ️  Could not retrieve browser logs")
        
        # Try to find specific episode elements
        episode_elements = [
            'h1[data-testid="entity-title"]',
            '[data-testid="episode-description"]',
            'h1',
            '[class*="episode"]',
            '[class*="title"]'
        ]
        
        print("🎯 Episode Element Search:")
        for selector in episode_elements:
            try:
                elements = browser.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    element_text = elements[0].text.strip()
                    print(f"   ✅ Found '{selector}': '{element_text[:50]}...'")
                else:
                    print(f"   ❌ Not found: '{selector}'")
            except Exception as e:
                print(f"   ⚠️  Error with '{selector}': {e}")
        
        # Save detailed analysis
        episode_id = spotify_url.split('/episode/')[-1].split('?')[0]
        analysis_file = f"/app/browser_analysis_{episode_id}.txt"
        
        with open(analysis_file, 'w', encoding='utf-8') as f:
            f.write(f"Spotify Browser Analysis Report\n")
            f.write(f"==============================\n\n")
            f.write(f"URL: {spotify_url}\n")
            f.write(f"Final URL: {current_url}\n")
            f.write(f"Title: {page_title}\n")
            f.write(f"User Agent: {user_agent}\n")
            f.write(f"Window Size: {window_size}\n")
            f.write(f"Cookies: {len(cookies)}\n")
            f.write(f"Page Length: {len(page_source)}\n\n")
            f.write("Content Indicators:\n")
            for indicator in spotify_indicators:
                found = "YES" if indicator in page_source else "NO"
                f.write(f"  {indicator}: {found}\n")
            f.write(f"\n--- PAGE SOURCE ---\n")
            f.write(page_source)
        
        print(f"💾 Detailed analysis saved to: {analysis_file}")
        
        return {
            "final_url": current_url,
            "title": page_title,
            "redirected": current_url != spotify_url,
            "page_length": len(page_source),
            "cookies_count": len(cookies),
            "user_agent": user_agent
        }
        
    except Exception as e:
        print(f"❌ Analysis error: {e}")
        return None

def main():
    spotify_url = "https://open.spotify.com/episode/4VqMqcy0wPAECv9M1s3kGy"
    
    print("🧪 Spotify Browser Difference Analysis")
    print("Comparing our automation vs real browser behavior")
    print("=" * 60)
    
    result = analyze_browser_differences(spotify_url)
    
    if result:
        print("=" * 60)
        print("📋 ANALYSIS SUMMARY:")
        print(f"Final URL: {result['final_url']}")
        print(f"Redirected: {result['redirected']}")
        print(f"Page Length: {result['page_length']} chars")
        print(f"Cookies: {result['cookies_count']}")
        print("=" * 60)
        print("💡 RECOMMENDATIONS:")
        if result['redirected']:
            print("- URL redirection detected - check redirect chain")
        if result['cookies_count'] == 0:
            print("- No cookies set - may need session/authentication")
        if result['page_length'] < 50000:
            print("- Small page size - likely getting minimal/error page")
        print("- Compare with real browser developer tools")

if __name__ == "__main__":
    main()