#!/usr/bin/env python3
"""
Advertisement Detection Service
Identifies and filters out promotional content from newsletters
"""

import re
import logging

class AdvertisementDetector:
    
    # Advertisement indicators
    AD_INDICATORS = {
        'ecommerce': [
            'add to cart', 'buy now', 'shop now', 'order now', 'purchase',
            'return policy', 'shipping', 'track order', 'size guide',
            'checkout', 'cart reminder', 'store locator', 'gift card'
        ],
        'marketing': [
            'marketing messages', 'promotional', 'unsubscribe', 'opt out',
            'never miss a drop', 'special offers', 'limited time',
            'exclusive deal', 'discount code', 'promo code', 'sale'
        ],
        'brand_promotion': [
            'discover new', 'latest collection', 'new arrivals',
            'follow us', 'join our', 'sign up for', 'newsletter signup'
        ],
        'legal_commercial': [
            'terms & privacy', 'msg & data rates', 'consent is not a condition',
            'recurring automated', 'reply stop', 'msg frequency varies'
        ]
    }
    
    # Minimum indicators required to classify as advertisement
    MIN_AD_INDICATORS = 3
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def is_advertisement(self, content, title=""):
        """
        Detect if content is an advertisement
        Returns: (is_ad, confidence_score, detected_indicators)
        """
        try:
            full_text = f"{title} {content}".lower()
            detected_indicators = []
            
            # Check for advertisement indicators
            for category, indicators in self.AD_INDICATORS.items():
                for indicator in indicators:
                    if indicator in full_text:
                        detected_indicators.append(f"{category}: {indicator}")
            
            # Calculate confidence score
            indicator_count = len(detected_indicators)
            confidence_score = min(indicator_count / self.MIN_AD_INDICATORS, 1.0)
            
            # Classify as advertisement if enough indicators found
            is_ad = indicator_count >= self.MIN_AD_INDICATORS
            
            if is_ad:
                self.logger.info(f"Advertisement detected: {indicator_count} indicators found")
                self.logger.debug(f"Detected indicators: {detected_indicators}")
            
            return is_ad, confidence_score, detected_indicators
            
        except Exception as e:
            self.logger.error(f"Error detecting advertisement: {e}")
            return False, 0.0, []
    
    def get_ad_reason(self, detected_indicators):
        """Get human-readable reason for advertisement classification"""
        if not detected_indicators:
            return "No advertisement indicators found"
        
        categories = {}
        for indicator in detected_indicators:
            category = indicator.split(':')[0]
            categories[category] = categories.get(category, 0) + 1
        
        reasons = []
        for category, count in categories.items():
            reasons.append(f"{count} {category.replace('_', ' ')} indicators")
        
        return f"Advertisement detected: {', '.join(reasons)}"