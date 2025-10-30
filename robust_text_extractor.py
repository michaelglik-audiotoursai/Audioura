#!/usr/bin/env python3
"""
Robust text extraction function to replace BeautifulSoup's problematic get_text() method
"""
from bs4 import BeautifulSoup
import re

def extract_clean_text(html_content, max_length=50000):
    """
    Extract clean text from HTML content, handling encoding issues gracefully
    
    Args:
        html_content: Raw HTML content (bytes or string)
        max_length: Maximum length of extracted text
        
    Returns:
        Clean text string without corruption markers
    """
    try:
        # Step 1: Handle encoding
        if isinstance(html_content, bytes):
            # Try UTF-8 first, fall back to latin-1 with replacement
            try:
                decoded_content = html_content.decode('utf-8', errors='strict')
            except UnicodeDecodeError:
                decoded_content = html_content.decode('utf-8', errors='replace')
        else:
            decoded_content = html_content
        
        # Step 2: Parse with BeautifulSoup
        soup = BeautifulSoup(decoded_content, 'html.parser')
        
        # Step 3: Remove problematic elements that often contain binary data
        for element in soup(['script', 'style', 'noscript', 'meta', 'link', 'head']):
            element.decompose()
        
        # Step 4: Extract text from content areas
        content_selectors = [
            'article', 'main', '.content', '.post', '.entry', 
            '[role="main"]', '.article-content', '.post-content'
        ]
        
        main_content = None
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        if not main_content:
            main_content = soup.find('body') or soup
        
        # Step 5: Get text with error handling
        try:
            raw_text = main_content.get_text(separator=' ', strip=True)
        except Exception:
            # Fallback: extract text from individual elements
            text_parts = []
            for element in main_content.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'li']):
                try:
                    element_text = element.get_text(strip=True)
                    if element_text:
                        text_parts.append(element_text)
                except Exception:
                    continue
            raw_text = ' '.join(text_parts)
        
        # Step 6: Clean the extracted text
        if not raw_text:
            return ""
        
        # Remove corruption markers and control characters
        clean_text = raw_text.replace('\ufffd', '')  # Remove replacement characters
        clean_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', clean_text)  # Remove control chars
        
        # Normalize whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Step 7: Validate text quality
        if len(clean_text) < 100:
            return clean_text  # Short text, return as-is
        
        # Check for excessive corruption (more than 5% non-printable chars)
        printable_chars = sum(1 for c in clean_text if c.isprintable() or c.isspace())
        corruption_ratio = 1 - (printable_chars / len(clean_text))
        
        if corruption_ratio > 0.05:  # More than 5% corruption
            # Try more aggressive cleaning
            clean_text = ''.join(c for c in clean_text if c.isprintable() or c.isspace())
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Step 8: Truncate if needed
        if len(clean_text) > max_length:
            clean_text = clean_text[:max_length].rsplit(' ', 1)[0] + '...'
        
        return clean_text
        
    except Exception as e:
        print(f"Error in extract_clean_text: {e}")
        return ""

def test_robust_extractor():
    """Test the robust text extractor with problematic content"""
    
    # Test with Guy Raz page if available
    try:
        with open('guyraz_page.html', 'rb') as f:
            guy_raz_content = f.read()
        
        print("Testing with Guy Raz page:")
        extracted = extract_clean_text(guy_raz_content)
        print(f"Length: {len(extracted)} chars")
        print(f"First 200 chars: {extracted[:200]}")
        print(f"Corruption markers: {extracted.count('\ufffd')}")
        print()
        
    except FileNotFoundError:
        print("Guy Raz page not found, skipping...")
    
    # Test with synthetic problematic content
    problematic_html = b'''<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<article>
<h1>Test Article</h1>
<p>This is clean content that should be extracted.</p>
<p>More clean content here.</p>
<div>Text with binary: \x80\x81\x82\x83\x84\x85 should be cleaned</div>
</article>
<script>var bad = "\x00\x01\x02\x03";</script>
</body>
</html>'''
    
    print("Testing with synthetic problematic content:")
    extracted = extract_clean_text(problematic_html)
    print(f"Length: {len(extracted)} chars")
    print(f"Content: {extracted}")
    print(f"Corruption markers: {extracted.count('\ufffd')}")

if __name__ == "__main__":
    test_robust_extractor()