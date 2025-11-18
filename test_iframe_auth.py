#!/usr/bin/env python3
"""
Test iframe-based Boston Globe Authentication
"""
import subprocess
import json

def test_iframe_authentication():
    """Test the iframe authentication in container"""
    print("TESTING IFRAME-BASED BOSTON GLOBE AUTHENTICATION")
    print("=" * 60)
    
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    test_article_url = "https://www.bostonglobe.com/2024/11/13/business/"
    
    print(f"Test Credentials: {credentials['username']} / {'*' * len(credentials['password'])}")
    print(f"Test Article: {test_article_url}")
    print()
    
    try:
        print("Step 1: Testing iframe authentication in container...")
        
        test_script = f"""
import sys
sys.path.append('/app')
from boston_globe_iframe_auth import authenticate_boston_globe_iframe
import json

credentials = {json.dumps(credentials)}
article_url = "{test_article_url}"

print("Starting iframe authentication test...")
try:
    result = authenticate_boston_globe_iframe(credentials, article_url)
    print("iframe Authentication result:", json.dumps(result, indent=2))
except Exception as e:
    print("iframe Authentication error:", str(e))
    import traceback
    traceback.print_exc()
"""
        
        with open('temp_iframe_test.py', 'w') as f:
            f.write(test_script)
        
        subprocess.run(['docker', 'cp', 'temp_iframe_test.py', 'newsletter-processor-1:/tmp/'], check=True)
        
        result = subprocess.run([
            'docker', 'exec', 'newsletter-processor-1', 
            'python3', '/tmp/temp_iframe_test.py'
        ], capture_output=True, text=True, timeout=180)
        
        print("iframe Authentication Test Output:")
        print(result.stdout)
        if result.stderr:
            print("Errors:")
            print(result.stderr)
        
        # Clean up
        import os
        try:
            os.remove('temp_iframe_test.py')
        except:
            pass
        
        print("\nStep 2: Checking for debug HTML files...")
        
        # Check for iframe debug files
        html_files = [
            '/tmp/boston_globe_iframe_debug.html',
            '/tmp/boston_globe_iframe_content.html',
            '/tmp/boston_globe_iframe_no_fields.html'
        ]
        
        for html_file in html_files:
            html_check = subprocess.run([
                'docker', 'exec', 'newsletter-processor-1',
                'ls', '-la', html_file
            ], capture_output=True, text=True)
            
            if html_check.returncode == 0:
                print(f"Found debug file: {html_file}")
                print(f"File info: {html_check.stdout.strip()}")
                
                # Copy HTML file for analysis
                local_filename = html_file.split('/')[-1]
                copy_result = subprocess.run([
                    'docker', 'cp', 
                    f'newsletter-processor-1:{html_file}',
                    local_filename
                ], capture_output=True, text=True)
                
                if copy_result.returncode == 0:
                    print(f"HTML file copied to: {local_filename}")
                else:
                    print(f"Failed to copy {html_file}")
            else:
                print(f"Debug file not found: {html_file}")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("Test timed out after 3 minutes")
        return False
    except Exception as e:
        print(f"Test failed: {e}")
        return False

def main():
    print("BOSTON GLOBE IFRAME AUTHENTICATION TESTING")
    print("This will test the iframe-aware authentication system")
    print()
    
    success = test_iframe_authentication()
    
    print("\n" + "=" * 60)
    print("TESTING SUMMARY")
    print("=" * 60)
    print(f"iframe Authentication: {'TESTED' if success else 'FAILED'}")
    print()
    print("HTML Files Created (if any):")
    print("  - boston_globe_iframe_debug.html (main login page)")
    print("  - boston_globe_iframe_content.html (iframe content)")
    print("  - boston_globe_iframe_no_fields.html (if no fields found)")
    print()
    print("Next Steps:")
    print("1. Examine the HTML files to see iframe content")
    print("2. Check if Piano/TinyPass authentication is working")
    print("3. Verify if login fields are found in iframe")

if __name__ == "__main__":
    main()