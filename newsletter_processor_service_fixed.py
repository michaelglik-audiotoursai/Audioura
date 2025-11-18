#!/usr/bin/env python3
"""
Newsletter Processor Service - MINIMAL Boston Globe Integration
"""
import os
import sys
import psycopg2
from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import re
from datetime import datetime, timedelta
import logging
import time
import json

# MINIMAL Boston Globe Authentication Integration
def authenticate_boston_globe_with_credentials(credentials, article_url):
    """Authenticate with Boston Globe using session-aware approach"""
    try:
        from boston_globe_session_auth import BostonGlobeSessionAuth
        
        auth = BostonGlobeSessionAuth()
        
        # Authenticate once and maintain session
        success = auth.authenticate_once(credentials['username'], credentials['password'])
        if not success:
            return {'success': False, 'error': 'Authentication failed'}
        
        # Extract article content using authenticated session
        result = auth.extract_article(article_url)
        auth.close()
        
        if result['success']:
            return {
                'success': True,
                'content': result['content'],
                'title': 'Boston Globe Article',
                'url': article_url
            }
        else:
            return {'success': False, 'error': result['error']}
            
    except Exception as e:
        logging.error(f"Boston Globe session authentication failed: {e}")
        return {'success': False, 'error': str(e)}

# Import the rest from the working backup
exec(open('newsletter_processor_service_backup.py').read())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5017, debug=True)