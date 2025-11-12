#!/usr/bin/env python3
"""
Subscription Detection Service
Detects subscription-required articles and extracts domain information
"""

import re
import logging
from urllib.parse import urlparse

class SubscriptionDetector:
    
    # Known subscription domains and their indicators
    SUBSCRIPTION_DOMAINS = {
        'bostonglobe.com': {
            'indicators': ['subscribe', 'subscription', 'premium', 'subscriber only'],
            'paywall_text': ['This article is available to subscribers', 'Subscribe to continue reading']
        },
        'nytimes.com': {
            'indicators': ['subscribe', 'subscription', 'premium'],
            'paywall_text': ['Subscribe to The New York Times', 'This article is for subscribers']
        },
        'wsj.com': {
            'indicators': ['subscribe', 'subscription', 'premium'],
            'paywall_text': ['Subscribe to The Wall Street Journal', 'This article is for subscribers']
        },
        'washingtonpost.com': {
            'indicators': ['subscribe', 'subscription', 'premium'],
            'paywall_text': ['Subscribe to The Washington Post', 'This article is for subscribers']
        }
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def detect_subscription_requirement(self, url, content):
        """
        Detect if an article requires subscription
        Returns: (is_subscription_required, domain)
        """
        try:
            # Extract domain from URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Check if domain is known subscription site
            if domain in self.SUBSCRIPTION_DOMAINS:
                # Check content for subscription indicators
                content_lower = content.lower()
                domain_config = self.SUBSCRIPTION_DOMAINS[domain]
                
                # Check for paywall text
                for paywall_text in domain_config['paywall_text']:
                    if paywall_text.lower() in content_lower:
                        self.logger.info(f"Subscription required detected for {domain}: paywall text found")
                        return True, domain
                
                # Check for subscription indicators
                for indicator in domain_config['indicators']:
                    if indicator in content_lower:
                        self.logger.info(f"Subscription required detected for {domain}: indicator '{indicator}' found")
                        return True, domain
                
                # If it's a known subscription domain but no clear indicators, assume subscription required
                self.logger.info(f"Subscription required detected for {domain}: known subscription domain")
                return True, domain
            
            # Check for generic subscription indicators in content
            generic_indicators = [
                'subscribe to continue',
                'subscription required',
                'premium content',
                'paywall',
                'subscriber exclusive',
                'members only'
            ]
            
            content_lower = content.lower()
            for indicator in generic_indicators:
                if indicator in content_lower:
                    self.logger.info(f"Generic subscription indicator found: {indicator}")
                    return True, domain
            
            return False, None
            
        except Exception as e:
            self.logger.error(f"Error detecting subscription requirement: {e}")
            return False, None
    
    def generate_device_encryption_key(self, device_id):
        """
        Generate encryption key for device (simplified for Stage 1)
        """
        import hashlib
        import secrets
        
        # Generate random key based on device ID and timestamp
        timestamp = str(int(time.time()))
        key_material = f"{device_id}_{timestamp}_{secrets.token_hex(16)}"
        
        # Create SHA-256 hash as encryption key
        encryption_key = hashlib.sha256(key_material.encode()).hexdigest()
        
        return encryption_key

import time