#!/usr/bin/env python3
"""
Test PDF Newsletter URL to analyze the issue
"""

import requests
import logging
from urllib.parse import urlparse

def test_pdf_url():
    """Test the PDF newsletter URL to understand the issue"""
    
    original_url = "https://click.kit-mail6.com/zlu5e07zw7u7ugp82oh6fwogmg00a6h35dnl/qvh8h7hr3ox962tg/aHR0cHM6Ly9kb3dubG9hZC5maWxla2l0Y2RuLmNvbS9kL2diaDFjZFl0M2I0cEJXenRDRmV2WmIvMllUaUVFdk50dlVmZGY2blNMbVQ5RA=="
    
    print("=== PDF NEWSLETTER ANALYSIS ===")
    print(f"Original URL: {original_url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # Follow redirects to see final destination
        response = requests.get(original_url, headers=headers, allow_redirects=True, timeout=10)
        
        print(f"Final URL: {response.url}")
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'Unknown')}")
        print(f"Content-Length: {len(response.content)} bytes")
        
        # Check if it's a PDF
        if 'pdf' in response.headers.get('Content-Type', '').lower():
            print("ISSUE IDENTIFIED: This is a PDF file, not HTML content!")
            print("PDF files cannot be processed as newsletter content.")
            return False
            
        # Check if content looks like binary
        try:
            text_content = response.text[:500]
            print(f"Content preview: {text_content}")
            
            # Check for PDF signature
            if response.content.startswith(b'%PDF'):
                print("CONFIRMED: File starts with PDF signature (%PDF)")
                return False
                
        except UnicodeDecodeError:
            print("ISSUE: Content is binary (cannot decode as text)")
            return False
            
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    test_pdf_url()