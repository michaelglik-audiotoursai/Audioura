#!/usr/bin/env python3
"""
Test Suite for Modularized Functions
Demonstrates isolated function testing
"""

import unittest
from newsletter_utils import clean_url, validate_content_length, detect_newsletter_platform
from content_extraction import extract_substack_content, extract_mailchimp_content

class TestNewsletterUtils(unittest.TestCase):
    
    def test_clean_url(self):
        """Test URL cleaning functionality"""
        # Test tracking parameter removal
        dirty_url = "https://example.com?utm_source=test&utm_campaign=email&et_rid=123"
        clean = clean_url(dirty_url)
        self.assertEqual(clean, "https://example.com")
        
        # Test multiple parameter cleanup
        messy_url = "https://example.com?param1=value1&utm_source=test&param2=value2"
        clean = clean_url(messy_url)
        self.assertNotIn("utm_source", clean)
        self.assertIn("param1=value1", clean)
    
    def test_validate_content_length(self):
        """Test content validation"""
        # Valid content
        valid_content = "This is a long enough piece of content that should pass the minimum length validation test."
        is_valid, message = validate_content_length(valid_content, min_length=50)
        self.assertTrue(is_valid)
        
        # Invalid content
        short_content = "Too short"
        is_valid, message = validate_content_length(short_content, min_length=50)
        self.assertFalse(is_valid)
        self.assertIn("too short", message.lower())
    
    def test_detect_newsletter_platform(self):
        """Test platform detection"""
        # Substack
        substack_url = "https://newsletter.substack.com/p/article"
        platform = detect_newsletter_platform(substack_url)
        self.assertEqual(platform, "substack")
        
        # MailChimp
        mailchimp_url = "https://mailchi.mp/example/newsletter"
        platform = detect_newsletter_platform(mailchimp_url)
        self.assertEqual(platform, "mailchimp")
        
        # Generic
        generic_url = "https://example.com/newsletter"
        platform = detect_newsletter_platform(generic_url)
        self.assertEqual(platform, "generic")

class TestContentExtraction(unittest.TestCase):
    
    def test_extract_substack_content(self):
        """Test Substack content extraction"""
        html = '''
        <div class="post-content">
            <p>This is the main content of the Substack newsletter.</p>
            <p>It contains multiple paragraphs with valuable information.</p>
        </div>
        '''
        content = extract_substack_content(html)
        self.assertIn("main content", content)
        self.assertGreater(len(content), 50)
    
    def test_extract_mailchimp_content(self):
        """Test MailChimp content extraction"""
        html = '''
        <div class="bodyContainer">
            <div class="mcnTextContent">
                <p>MailChimp newsletter content here.</p>
                <p>Multiple paragraphs of newsletter information.</p>
            </div>
        </div>
        '''
        content = extract_mailchimp_content(html)
        self.assertIn("MailChimp newsletter", content)
        self.assertGreater(len(content), 30)
        
        # Debug: print content if test fails
        if not content:
            print(f"DEBUG: No content extracted from HTML: {html[:100]}...")

if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)