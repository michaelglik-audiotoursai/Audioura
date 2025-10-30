#!/usr/bin/env python3
"""
Isolated test case to replicate and fix BeautifulSoup encoding issue
"""
import os
from bs4 import BeautifulSoup
import re

def test_encoding_problem():
    """Test the exact encoding problem with Guy Raz page"""
    
    # Load the problematic HTML file
    html_file = "guyraz_page.html"
    if not os.path.exists(html_file):
        print(f"Error: {html_file} not found")
        return
    
    print("=== Testing BeautifulSoup Encoding Problem ===")
    
    # Read raw bytes
    with open(html_file, 'rb') as f:
        raw_content = f.read()
    
    print(f"File size: {len(raw_content)} bytes")
    
    # Method 1: Current approach (fails)
    print("\n1. Current approach (reproduces problem):")
    try:
        soup = BeautifulSoup(raw_content, 'html.parser')
        main_content = soup.find('body') or soup
        article_content = main_content.get_text(separator=' ', strip=True)
        
        print(f"Length: {len(article_content)} chars")
        print(f"First 200 chars: {repr(article_content[:200])}")
        
        # Check for corruption
        corruption_count = article_content.count('\ufffd')
        print(f"Corruption markers (\\ufffd): {corruption_count}")
        
    except Exception as e:
        print(f"Failed: {e}")
    
    # Method 2: Try different encodings
    print("\n2. Testing different encodings:")
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            decoded_content = raw_content.decode(encoding, errors='replace')
            soup = BeautifulSoup(decoded_content, 'html.parser')
            main_content = soup.find('body') or soup
            article_content = main_content.get_text(separator=' ', strip=True)
            
            corruption_count = article_content.count('\ufffd')
            print(f"  {encoding}: {len(article_content)} chars, {corruption_count} corruptions")
            
            if corruption_count == 0:
                print(f"  SUCCESS with {encoding}!")
                print(f"  First 200 chars: {article_content[:200]}")
                return encoding, article_content
                
        except Exception as e:
            print(f"  {encoding}: Failed - {e}")
    
    # Method 3: Try cleaning before parsing
    print("\n3. Testing content cleaning approaches:")
    
    try:
        # Remove problematic bytes
        cleaned_content = raw_content.replace(b'\x00', b'')  # Remove null bytes
        cleaned_content = re.sub(rb'[\x80-\xff]', b'', cleaned_content)  # Remove high bytes
        
        soup = BeautifulSoup(cleaned_content, 'html.parser')
        main_content = soup.find('body') or soup
        article_content = main_content.get_text(separator=' ', strip=True)
        
        corruption_count = article_content.count('\ufffd')
        print(f"  Byte cleaning: {len(article_content)} chars, {corruption_count} corruptions")
        
        if corruption_count == 0:
            print(f"  SUCCESS with byte cleaning!")
            print(f"  First 200 chars: {article_content[:200]}")
            return "byte_cleaning", article_content
            
    except Exception as e:
        print(f"  Byte cleaning failed: {e}")
    
    # Method 4: Extract title from HTML instead
    print("\n4. Fallback: Extract title from HTML:")
    try:
        soup = BeautifulSoup(raw_content, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            print(f"  HTML title: {title}")
            return "html_title", title
    except Exception as e:
        print(f"  Title extraction failed: {e}")
    
    print("\nAll methods failed to fix encoding issue")
    return None, None

def proposed_fix():
    """Proposed fix for the encoding issue"""
    
    html_file = "guyraz_page.html"
    if not os.path.exists(html_file):
        print("HTML file not found")
        return None
    
    with open(html_file, 'rb') as f:
        raw_content = f.read()
    
    # Try multiple encoding strategies
    strategies = [
        ('utf-8', 'strict'),
        ('utf-8', 'replace'), 
        ('latin-1', 'replace'),
        ('cp1252', 'replace')
    ]
    
    for encoding, error_handling in strategies:
        try:
            decoded_content = raw_content.decode(encoding, errors=error_handling)
            soup = BeautifulSoup(decoded_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
                script.decompose()
            
            # Try to find main content area
            main_content = None
            for selector in ['article', 'main', '.content', '.post', '.entry', '[role="main"]']:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            if not main_content:
                main_content = soup.find('body') or soup
            
            # Extract text with error handling
            try:
                article_content = main_content.get_text(separator=' ', strip=True)
                
                # Clean up extra whitespace
                article_content = re.sub(r'\s+', ' ', article_content).strip()
                
                # Check for corruption
                corruption_count = article_content.count('\ufffd')
                
                if corruption_count == 0 and len(article_content) > 1000:
                    print(f"SUCCESS: {encoding} with {error_handling}")
                    print(f"Content length: {len(article_content)} chars")
                    print(f"First 300 chars: {article_content[:300]}")
                    return article_content
                    
            except Exception as text_error:
                print(f"Text extraction failed for {encoding}: {text_error}")
                continue
                
        except Exception as decode_error:
            print(f"Decoding failed for {encoding}: {decode_error}")
            continue
    
    print("All encoding strategies failed")
    return None

if __name__ == "__main__":
    print("Testing encoding problem...")
    method, content = test_encoding_problem()
    
    if content and '\ufffd' not in content:
        print(f"\nSolution found using: {method}")
    else:
        print(f"\nTesting proposed fix...")
        fixed_content = proposed_fix()
        if fixed_content:
            print("Fix successful!")
        else:
            print("Fix failed - need alternative approach")