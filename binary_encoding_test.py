#!/usr/bin/env python3
"""
Test to reproduce BeautifulSoup getText() encoding problem with binary data
"""
from bs4 import BeautifulSoup

def test_binary_encoding_problem():
    """Create HTML with embedded binary data that causes getText() to fail"""
    
    print("=== Binary Data Encoding Test ===")
    
    # Create HTML with problematic binary sequences that cause corruption
    problematic_html = b'''<!DOCTYPE html>
<html>
<head><title>Test Page with Binary Data</title></head>
<body>
<div class="content">
<p>Normal text before binary data.</p>
<div>Text with embedded binary: \x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f\x90\x91\x92\x93\x94\x95\x96\x97\x98\x99\x9a\x9b\x9c\x9d\x9e\x9f more text</div>
<p>More text after binary data.</p>
<script type="text/javascript">
// JavaScript with binary data (common in minified scripts)
var data = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f";
var more = "\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f\x90\x91\x92\x93\x94\x95\x96\x97\x98\x99\x9a\x9b\x9c\x9d\x9e\x9f";
</script>
<style>
/* CSS with binary data */
.test::before { content: "\x80\x81\x82\x83\x84\x85"; }
</style>
</div>
</body>
</html>'''
    
    print(f"HTML content size: {len(problematic_html)} bytes")
    
    # Test 1: Current approach (should fail)
    print("\n1. Testing current approach (reproducing the problem):")
    try:
        soup = BeautifulSoup(problematic_html, 'html.parser')
        main_content = soup.find('body') or soup
        
        # This is the exact line that fails in newsletter_processor_service.py
        article_content = main_content.get_text(separator=' ', strip=True)
        
        print(f"Extracted text length: {len(article_content)} chars")
        print(f"First 200 chars: {repr(article_content[:200])}")
        
        # Count corruption markers
        corruption_count = article_content.count('\ufffd')
        print(f"Corruption markers: {corruption_count}")
        
        if corruption_count > 0:
            print("SUCCESS: Reproduced the encoding problem!")
            return True
        else:
            print("No corruption detected - may need more problematic data")
            
    except Exception as e:
        print(f"Error with current approach: {e}")
    
    # Test 2: Alternative approach with explicit encoding
    print("\n2. Testing fix with explicit UTF-8 decoding:")
    try:
        # Decode with error handling first
        decoded_content = problematic_html.decode('utf-8', errors='replace')
        soup = BeautifulSoup(decoded_content, 'html.parser')
        
        # Remove problematic elements that often contain binary data
        for element in soup(['script', 'style', 'noscript']):
            element.decompose()
        
        main_content = soup.find('body') or soup
        article_content = main_content.get_text(separator=' ', strip=True)
        
        print(f"Fixed text length: {len(article_content)} chars")
        print(f"First 200 chars: {repr(article_content[:200])}")
        
        corruption_count = article_content.count('\ufffd')
        print(f"Corruption markers after fix: {corruption_count}")
        
        if corruption_count < 5:  # Allow some corruption but much less
            print("Fix appears to work - significantly reduced corruption!")
        else:
            print(f"Still has {corruption_count} corruption markers")
            
    except Exception as e:
        print(f"Error with fix attempt: {e}")
    
    # Test 3: More aggressive cleaning
    print("\n3. Testing aggressive text cleaning:")
    try:
        decoded_content = problematic_html.decode('utf-8', errors='replace')
        soup = BeautifulSoup(decoded_content, 'html.parser')
        
        # Remove all potentially problematic elements
        for element in soup(['script', 'style', 'noscript', 'meta', 'link']):
            element.decompose()
        
        # Get text from specific content areas only
        content_areas = soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span'])
        
        clean_text_parts = []
        for area in content_areas:
            text = area.get_text(separator=' ', strip=True)
            # Filter out text with high corruption
            if text and text.count('\ufffd') / len(text) < 0.1:  # Less than 10% corruption
                clean_text_parts.append(text)
        
        article_content = ' '.join(clean_text_parts)
        
        print(f"Aggressively cleaned text length: {len(article_content)} chars")
        print(f"First 200 chars: {repr(article_content[:200])}")
        
        corruption_count = article_content.count('\ufffd')
        print(f"Corruption markers after aggressive cleaning: {corruption_count}")
        
    except Exception as e:
        print(f"Error with aggressive cleaning: {e}")
    
    return False

if __name__ == "__main__":
    test_binary_encoding_problem()