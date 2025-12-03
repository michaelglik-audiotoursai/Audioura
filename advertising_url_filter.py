#!/usr/bin/env python3
"""
Advertising URL Filter - Enhanced filtering to prevent processing advertising sites
"""

import logging
from urllib.parse import urlparse

class AdvertisingURLFilter:
    def __init__(self):
        # Comprehensive list of advertising and tracking domains
        self.advertising_domains = [
            # Travel/Booking Sites
            'booking.com',
            'expedia.com', 
            'hotels.com',
            'priceline.com',
            'kayak.com',
            'tripadvisor.com',
            
            # E-commerce
            'amazon.com',
            'ebay.com',
            'walmart.com',
            'target.com',
            
            # Ad Networks & Tracking
            'googleadservices.com',
            'doubleclick.net',
            'googlesyndication.com',
            'adsystem.com',
            'amazon-adsystem.com',
            'liadm.com',
            'outbrain.com',
            'taboola.com',
            'criteo.com',
            
            # Social Media (when used for ads)
            'facebook.com/tr',
            'instagram.com/ads',
            'twitter.com/i/ads',
            'linkedin.com/ads',
            
            # Analytics & Tracking
            'google-analytics.com',
            'googletagmanager.com',
            'hotjar.com',
            'mixpanel.com',
            'segment.com',
            
            # Email Marketing Redirects
            'mailchi.mp/redirect',
            'constantcontact.com/redirect',
            'campaign-archive.com',
            
            # Generic Ad Indicators
            'ads.',
            'ad.',
            'advertising.',
            'promo.',
            'promotion.',
            'offer.',
            'deals.',
            'shop.',
            'store.',
            'buy.'
        ]
        
        # URL path patterns that indicate advertising
        self.advertising_path_patterns = [
            '/ads/',
            '/advertising/',
            '/promo/',
            '/promotion/',
            '/offer/',
            '/deals/',
            '/shop/',
            '/store/',
            '/buy/',
            '/redirect/',
            '/click/',
            '/track/',
            '/affiliate/',
            '/partner/',
            '/sponsor/'
        ]
        
        # Query parameter patterns that indicate tracking/advertising
        self.advertising_query_patterns = [
            'utm_source',
            'utm_medium', 
            'utm_campaign',
            'affiliate',
            'partner',
            'promo',
            'offer',
            'deal',
            'discount',
            'coupon',
            'ref=',
            'referrer=',
            'click_id',
            'campaign_id'
        ]
    
    def is_advertising_url(self, url):
        """
        Check if URL is likely an advertising or promotional site
        Returns: (is_advertising, reason)
        """
        try:
            if not url or not isinstance(url, str):
                return False, "Invalid URL"
            
            parsed = urlparse(url.lower())
            
            # Check domain against advertising domains
            for ad_domain in self.advertising_domains:
                if ad_domain in parsed.netloc:
                    return True, f"Advertising domain detected: {ad_domain}"
            
            # Check path for advertising patterns
            for pattern in self.advertising_path_patterns:
                if pattern in parsed.path:
                    return True, f"Advertising path pattern detected: {pattern}"
            
            # Check query parameters for advertising indicators
            if parsed.query:
                query_lower = parsed.query.lower()
                for pattern in self.advertising_query_patterns:
                    if pattern in query_lower:
                        return True, f"Advertising query parameter detected: {pattern}"
            
            return False, "Clean URL"
            
        except Exception as e:
            logging.error(f"Error checking advertising URL {url}: {e}")
            return True, f"Error analyzing URL: {str(e)}"  # Err on side of caution
    
    def filter_urls(self, urls):
        """
        Filter out advertising URLs from a list
        Returns: (clean_urls, filtered_urls)
        """
        clean_urls = []
        filtered_urls = []
        
        for url in urls:
            is_ad, reason = self.is_advertising_url(url)
            if is_ad:
                filtered_urls.append({
                    'url': url,
                    'reason': reason
                })
                logging.info(f"FILTERED advertising URL: {url} - {reason}")
            else:
                clean_urls.append(url)
        
        return clean_urls, filtered_urls
    
    def is_legitimate_news_url(self, url):
        """
        Check if URL is from a legitimate news source
        """
        legitimate_news_domains = [
            'bostonglobe.com',
            'nytimes.com',
            'washingtonpost.com',
            'reuters.com',
            'ap.org',
            'bbc.com',
            'cnn.com',
            'npr.org',
            'pbs.org',
            'wsj.com',
            'bloomberg.com',
            'cnbc.com',
            'newtonbeacon.org',
            'boston.com',
            'wbur.org',
            'wcvb.com',
            'nbcboston.com'
        ]
        
        try:
            parsed = urlparse(url.lower())
            return any(domain in parsed.netloc for domain in legitimate_news_domains)
        except:
            return False
    
    def validate_boston_globe_tracking_url(self, tracking_url, final_url):
        """
        Validate that Boston Globe tracking URL resolves to legitimate content
        """
        if not tracking_url.startswith('https://click.email.bostonglobe.com'):
            return False, "Not a Boston Globe tracking URL"
        
        # Check if final URL is legitimate
        if self.is_legitimate_news_url(final_url):
            return True, "Resolves to legitimate news site"
        
        is_ad, reason = self.is_advertising_url(final_url)
        if is_ad:
            return False, f"Resolves to advertising site: {reason}"
        
        return True, "Appears to be legitimate content"

def test_advertising_filter():
    """Test the advertising URL filter"""
    filter = AdvertisingURLFilter()
    
    test_urls = [
        # Legitimate URLs
        "https://www.bostonglobe.com/2024/11/27/business/article-title",
        "https://www.nytimes.com/2024/11/27/politics/article-title",
        
        # Advertising URLs that should be filtered
        "https://www.booking.com/hotel/us/bend-campfire-hotel.html",
        "https://liadm.com/redirect?url=example",
        "https://amazon.com/product/example",
        "https://googleadservices.com/ads/example",
        
        # Tracking URLs with advertising parameters
        "https://example.com/article?utm_source=email&utm_campaign=promo",
        "https://example.com/shop/deals/special-offer"
    ]
    
    clean_urls, filtered_urls = filter.filter_urls(test_urls)
    
    print("CLEAN URLs:")
    for url in clean_urls:
        print(f"  ✅ {url}")
    
    print("\nFILTERED URLs:")
    for item in filtered_urls:
        print(f"  ❌ {item['url']} - {item['reason']}")

if __name__ == "__main__":
    test_advertising_filter()