#!/usr/bin/env python3
"""
Advertising URL Filter - Enhanced filtering to prevent processing advertising sites
"""

import logging
from urllib.parse import urlparse, parse_qs

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
            # Match against parameter *names* only (not values or raw query string)
            # to avoid false positives on URLs like ?topic=offering or ?q=promotion+news
            if parsed.query:
                query_keys = {k.lower() for k in parse_qs(parsed.query, keep_blank_values=True).keys()}
                for pattern in self.advertising_query_patterns:
                    if pattern in query_keys:
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
    """Regression test — raises AssertionError on any misclassification."""
    f = AdvertisingURLFilter()

    CLEAN = [
        # Legitimate news sites
        "https://www.bostonglobe.com/2024/11/27/business/article-title",
        "https://www.nytimes.com/2024/11/27/politics/article-title",
        # Newsletter attribution tags — must NOT be filtered
        "https://www.reloadnyc.com/?ref=artificial-commonsense-newsletter",
        "https://somesite.com/article?referrer=newsletter-weekly",
        # Legitimate query params whose values contain ad-pattern words
        "https://example.com/article?topic=offering",
        "https://example.com/search?q=promotion+impact",
        "https://example.com/recipe?topic=dealing-with-leftovers",
        "https://example.com/news?topic=partnerships",
    ]

    AD = [
        # Advertising domains
        "https://www.booking.com/hotel/us/bend-campfire-hotel.html",
        "https://liadm.com/redirect?url=example",
        "https://amazon.com/product/example",
        "https://googleadservices.com/ads/example",
        # Real UTM / affiliate query params
        "https://example.com/article?utm_source=email&utm_campaign=spring",
        "https://example.com/?affiliate=acmecorp",
        "https://example.com/?click_id=abc123",
        # Advertising path patterns
        "https://example.com/shop/deals/special-offer",
    ]

    for url in CLEAN:
        is_ad, reason = f.is_advertising_url(url)
        assert not is_ad, f"FALSE POSITIVE: {url} -> {reason}"

    for url in AD:
        is_ad, reason = f.is_advertising_url(url)
        assert is_ad, f"FALSE NEGATIVE: {url} was not flagged"

    print(f"OK — {len(CLEAN)} clean + {len(AD)} ad URLs all classified correctly")

if __name__ == "__main__":
    test_advertising_filter()