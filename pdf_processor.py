#!/usr/bin/env python3
"""
PDF Processing Module
Extract text content from PDF newsletters
"""

import requests
import logging
from io import BytesIO

def extract_pdf_text(pdf_url):
    """Extract text from PDF URL"""
    try:
        # Try importing PDF processing libraries
        try:
            import PyPDF2
        except ImportError:
            return {
                'success': False,
                'error': 'PDF processing not available. PyPDF2 library not installed.',
                'suggestion': 'Install with: pip install PyPDF2'
            }
        
        # Download PDF content
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(pdf_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Extract text from PDF
        pdf_file = BytesIO(response.content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text_content = ""
        for page in pdf_reader.pages:
            text_content += page.extract_text() + "\n"
        
        if len(text_content.strip()) < 100:
            return {
                'success': False,
                'error': 'PDF text extraction failed or insufficient content',
                'content_length': len(text_content)
            }
        
        return {
            'success': True,
            'content': text_content.strip(),
            'content_length': len(text_content),
            'pages': len(pdf_reader.pages)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'PDF processing failed: {str(e)}'
        }

def should_attempt_pdf_processing(pdf_url, file_size_mb=None):
    """Determine if PDF processing should be attempted"""
    
    # Check file size if available
    if file_size_mb and file_size_mb > 50:
        return False, "PDF file too large (>50MB)"
    
    # Check if it's a newsletter-like PDF
    if 'newsletter' in pdf_url.lower() or 'digest' in pdf_url.lower():
        return True, "Newsletter-like PDF detected"
    
    return True, "PDF processing available"