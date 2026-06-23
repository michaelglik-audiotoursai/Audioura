#!/usr/bin/env python3
"""
Test Enhanced Boston Globe Authentication
Tests the integrated authentication system and captures HTML for analysis
"""
import requests
import json
import time

def test_enhanced_authentication():
    """Test the enhanced Boston Globe authentication system"""
    print("🔍 TESTING ENHANCED BOSTON GLOBE AUTHENTICATION")
    print("=" * 60)
    
    # Test credentials
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    # Test article URL
    test_article_url = "https://www.bostonglobe.com/2024/11/13/business/"
    
    print(f"Test Credentials: {credentials['username']} / {'*' * len(credentials['password'])}")
    print(f"Test Article: {test_article_url}")
    print()
    
    try:
        # Test the authentication function directly
        print("📍 Step 1: Testing authentication function in container...")
        
        test_script = f"""
import sys
sys.path.append('/app')
from newsletter_processor_service import authenticate_boston_globe_enhanced
import json

credentials = {json.dumps(credentials)}
article_url = "{test_article_url}"

print("Starting authentication test...")
result = authenticate_boston_globe_enhanced(credentials, article_url)
print("Authentication result:", json.dumps(result, indent=2))
"""
        
        # Write test script to container
        with open('temp_auth_test.py', 'w') as f:
            f.write(test_script)
        
        # Copy and run test script
        import subprocess
        subprocess.run(['docker', 'cp', 'temp_auth_test.py', 'newsletter-processor-1:/tmp/'], check=True)
        
        result = subprocess.run([
            'docker', 'exec', 'newsletter-processor-1', 
            'python3', '/tmp/temp_auth_test.py'
        ], capture_output=True, text=True, timeout=120)
        
        print("📄 Authentication Test Output:")
        print(result.stdout)
        if result.stderr:
            print("⚠️  Errors:")
            print(result.stderr)
        
        # Clean up
        import os
        try:
            os.remove('temp_auth_test.py')
        except:
            pass
        
        print("\n" + "=" * 60)
        print("✅ Enhanced authentication test completed!")
        
        # Check if HTML debug file was created
        print("\n📍 Step 2: Checking for debug HTML file...")
        
        html_check = subprocess.run([
            'docker', 'exec', 'newsletter-processor-1',
            'ls', '-la', '/tmp/boston_globe_login_debug.html'
        ], capture_output=True, text=True)
        
        if html_check.returncode == 0:
            print("✅ Debug HTML file created!")
            print("📁 File info:", html_check.stdout.strip())
            
            # Copy HTML file for analysis
            copy_result = subprocess.run([
                'docker', 'cp', 
                'newsletter-processor-1:/tmp/boston_globe_login_debug.html',
                'boston_globe_login_captured.html'
            ], capture_output=True, text=True)
            
            if copy_result.returncode == 0:
                print("✅ HTML file copied to: boston_globe_login_captured.html")
                print("📋 You can now examine this file to see what Boston Globe shows us")
            else:
                print("❌ Failed to copy HTML file")
        else:
            print("⚠️  No debug HTML file found")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ Test timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def capture_boston_globe_html_simple():
    """Capture Boston Globe HTML using simple requests for comparison"""
    print("\n📍 Step 3: Capturing Boston Globe HTML with simple requests...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    urls = [
        ('login_page', 'https://www.bostonglobe.com/login'),
        ('homepage', 'https://www.bostonglobe.com/'),
        ('sample_article', 'https://www.bostonglobe.com/2024/11/13/business/')
    ]
    
    for name, url in urls:
        try:
            print(f"   📄 Capturing: {name}")
            response = requests.get(url, headers=headers, timeout=10)
            
            filename = f"boston_globe_{name}_simple.html"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Captured with simple requests -->\n")
                f.write(f"<!-- URL: {url} -->\n")
                f.write(f"<!-- Status: {response.status_code} -->\n")
                f.write(response.text)
            
            print(f"   ✅ Saved: {filename} ({response.status_code}, {len(response.text)} chars)")
            
            # Quick analysis
            content = response.text.lower()
            indicators = []
            if 'email' in content:
                indicators.append('email')
            if 'password' in content:
                indicators.append('password')
            if 'tinypass' in content:
                indicators.append('tinypass')
            if 'auth.bostonglobe' in content:
                indicators.append('auth.bostonglobe')
            
            if indicators:
                print(f"   🔍 Found: {', '.join(indicators)}")
            
        except Exception as e:
            print(f"   ❌ Failed to capture {name}: {e}")
        
        time.sleep(1)

def main():
    """Run comprehensive Boston Globe authentication testing"""
    print("🚀 BOSTON GLOBE PHASE 2 AUTHENTICATION TESTING")
    print("This will test enhanced authentication and capture HTML pages")
    print()
    
    # Test 1: Enhanced authentication
    auth_success = test_enhanced_authentication()
    
    # Test 2: Simple HTML capture for comparison
    capture_boston_globe_html_simple()
    
    print("\n" + "=" * 60)
    print("📋 TESTING SUMMARY")
    print("=" * 60)
    print(f"Enhanced Authentication: {'✅ TESTED' if auth_success else '❌ FAILED'}")
    print("HTML Files Created:")
    print("  - boston_globe_login_captured.html (from browser automation)")
    print("  - boston_globe_login_page_simple.html (from simple requests)")
    print("  - boston_globe_homepage_simple.html (from simple requests)")
    print("  - boston_globe_sample_article_simple.html (from simple requests)")
    print()
    print("📄 Next Steps:")
    print("1. Examine the HTML files to understand Boston Globe's login system")
    print("2. Compare browser automation vs simple requests")
    print("3. Identify the specific authentication challenges")
    print("4. Enhance the authentication system based on findings")

if __name__ == "__main__":
    main()