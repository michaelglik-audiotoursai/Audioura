#!/usr/bin/env python3
"""
Simple test to reproduce BeautifulSoup getText() encoding problem
"""
from bs4 import BeautifulSoup
import os

def test_simple_encoding_problem():
    """Create a simple test case that reproduces the encoding issue"""
    
    print("=== Simple BeautifulSoup Encoding Test ===")
    
    # Check if we have the Guy Raz HTML file
    html_file = "guyraz_page.html"
    if os.path.exists(html_file):
        print(f"Using existing {html_file}")
        with open(html_file, 'rb') as f:
            html_content = f.read()
    else:
        print("Creating synthetic problematic HTML content")
        # Create HTML with embedded binary data that causes problems
        html_content = b'''<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<div class="content">
<p>This is normal text content.</p>
<p>Here comes problematic content with binary data:</p>
<div>Some text \x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f more text</div>
<p>More normal content after binary data.</p>
<script>
// Some JavaScript with binary data
var data = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f";
</script>
</div>
</body>
</html>'''
    
    print(f"HTML content size: {len(html_content)} bytes")
    
    # Test 1: Current approach that fails
    print("\n1. Testing current approach (should show corruption):")
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        main_content = soup.find('body') or soup
        
        # This is the exact line that fails in newsletter_processor_service.py
        article_content = main_content.get_text(separator=' ', strip=True)
        
        print(f"Extracted text length: {len(article_content)} chars")
        print(f"First 200 chars: {repr(article_content[:200])}")
        
        # Count corruption markers
        corruption_count = article_content.count('\ufffd')
        print(f"Corruption markers (\\ufffd): {corruption_count}")
        
        if corruption_count > 0:
            print("✅ SUCCESS: Reproduced the encoding problem!")
            return True
        else:
            print("❌ No corruption detected with current approach")
            
    except Exception as e:
        print(f"❌ Error with current approach: {e}")
    
    # Test 2: Try to fix with encoding handling
    print("\n2. Testing potential fix:")
    try:
        # Decode with error handling first
        decoded_content = html_content.decode('utf-8', errors='replace')
        soup = BeautifulSoup(decoded_content, 'html.parser')
        
        # Remove problematic elements
        for script in soup(['script', 'style']):
            script.decompose()
        
        main_content = soup.find('body') or soup
        article_content = main_content.get_text(separator=' ', strip=True)
        
        print(f"Fixed text length: {len(article_content)} chars")
        print(f"First 200 chars: {repr(article_content[:200])}")
        
        corruption_count = article_content.count('\ufffd')
        print(f"Corruption markers after fix: {corruption_count}")
        
        if corruption_count == 0:
            print("✅ Fix appears to work!")
        else:
            print(f"⚠️ Still has {corruption_count} corruption markers")
            
    except Exception as e:
        print(f"❌ Error with fix attempt: {e}")
    
    return False

if __name__ == "__main__":
    test_simple_encoding_problem()