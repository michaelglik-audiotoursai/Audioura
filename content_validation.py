#!/usr/bin/env python3
"""
Content Validation Module
Detects and rejects unsupported content types like PDFs
"""

import requests
import logging
from urllib.parse import urlparse

def validate_newsletter_url(url):
    """Validate if URL points to processable newsletter content"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # Get headers only first to check content type
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
        content_type = response.headers.get('Content-Type', '').lower()
        
        # Check for PDF content - offer processing option
        if 'pdf' in content_type:
            return {
                'valid': False,
                'error_type': 'pdf_content_detected',
                'message': f'PDF newsletter detected. PDF processing requires additional tools and may have limited accuracy. Would you like to attempt PDF text extraction?',
                'final_url': response.url,
                'content_type': content_type,
                'processing_options': ['reject', 'attempt_pdf_extraction']
            }
        
        if 'application/' in content_type and 'html' not in content_type:
            return {
                'valid': False,
                'error_type': 'unsupported_content_type', 
                'message': f'Unsupported content type: {content_type}. Only HTML newsletters are supported.',
                'final_url': response.url
            }
            
        # If HEAD request doesn't give content-type, try GET with limited bytes
        if not content_type or content_type == 'application/octet-stream':
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10, stream=True)
            
            # Read first 1024 bytes to check for PDF signature
            chunk = response.raw.read(1024)
            if chunk.startswith(b'%PDF'):
                return {
                    'valid': False,
                    'error_type': 'unsupported_content_type',
                    'message': 'PDF file detected. PDF newsletters are not supported. Please provide an HTML newsletter URL instead.',
                    'final_url': response.url
                }
        
        return {
            'valid': True,
            'content_type': content_type,
            'final_url': response.url
        }
        
    except Exception as e:
        return {
            'valid': False,
            'error_type': 'network_error',
            'message': f'Unable to validate newsletter URL: {str(e)}',
            'final_url': url
        }

def detect_garbage_content(content):
    """Detect if extracted content is garbage/binary data"""
    
    if not content or len(content.strip()) < 50:
        return True, "Content too short or empty"
    
    # Check for high ratio of non-printable characters
    printable_chars = sum(1 for c in content if c.isprintable() or c.isspace())
    if len(content) > 0 and (printable_chars / len(content)) < 0.7:
        return True, "Content contains too many non-printable characters (likely binary data)"
    
    # Check for PDF-like content
    if '%PDF' in content or 'endobj' in content or '/Type /Catalog' in content:
        return True, "Content appears to be PDF data"
    
    # Check for repetitive garbage patterns
    if len(set(content.replace(' ', '').replace('\n', ''))) < 10:
        return True, "Content appears to be repetitive garbage"
    
    return False, "Content appears valid"

def validate_extracted_content(content, min_length=100):
    """Validate extracted content quality"""
    
    # Check if content is garbage
    is_garbage, garbage_reason = detect_garbage_content(content)
    if is_garbage:
        return {
            'valid': False,
            'error_type': 'garbage_content',
            'message': f'Extracted content is not readable: {garbage_reason}',
            'content_length': len(content) if content else 0
        }
    
    # Check minimum length
    if len(content.strip()) < min_length:
        return {
            'valid': False,
            'error_type': 'insufficient_content',
            'message': f'Content too short: {len(content)} chars (minimum: {min_length})',
            'content_length': len(content)
        }
    
    return {
        'valid': True,
        'content_length': len(content),
        'message': f'Content validated: {len(content)} chars'
    }