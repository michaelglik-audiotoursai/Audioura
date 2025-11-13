#!/usr/bin/env python3
"""
Boston Globe Diagnostic Tool
Analyze page content after authentication
"""

import time
import logging
from selenium.webdriver.common.by import By
from boston_globe_session_auth import BostonGlobeSessionAuth

class BostonGlobeDiagnostic(BostonGlobeSessionAuth):
    
    def diagnose_page(self, article_url):
        """Diagnose what's on the page after authentication"""
        if not self.authenticated:
            return {"success": False, "error": "Not authenticated"}
            
        try:
            self.driver.get(article_url)
            time.sleep(5)
            
            # Get page info
            page_info = {
                "url": self.driver.current_url,
                "title": self.driver.title,
                "page_source_length": len(self.driver.page_source)
            }
            
            # Check for paywall indicators
            paywall_check = self._check_paywall()
            
            # Try different content selectors
            content_analysis = self._analyze_content_selectors()
            
            # Get all text content
            all_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # Save debug HTML
            debug_file = f"/tmp/bg_diagnostic_{int(time.time())}.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
                
            return {
                "success": True,
                "page_info": page_info,
                "paywall_check": paywall_check,
                "content_analysis": content_analysis,
                "total_text_length": len(all_text),
                "text_preview": all_text[:500],
                "debug_file": debug_file
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def _check_paywall(self):
        """Check for paywall indicators"""
        indicators = {
            "subscribe_text": "subscribe" in self.driver.page_source.lower(),
            "paywall_class": bool(self.driver.find_elements(By.CSS_SELECTOR, ".paywall, .subscription-required")),
            "login_required": "log in" in self.driver.page_source.lower(),
            "premium_content": "premium" in self.driver.page_source.lower()
        }
        return indicators
        
    def _analyze_content_selectors(self):
        """Test different content selectors"""
        selectors = [
            ".story-body-text",
            ".article-body", 
            "[data-module='ArticleBody']",
            ".paywall-content",
            "article",
            ".content",
            ".story-content",
            "main",
            "p"
        ]
        
        results = {}
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    total_text = " ".join([el.text.strip() for el in elements if el.text.strip()])
                    results[selector] = {
                        "element_count": len(elements),
                        "text_length": len(total_text),
                        "preview": total_text[:100] if total_text else "No text"
                    }
                else:
                    results[selector] = {"element_count": 0, "text_length": 0, "preview": "No elements"}
            except Exception as e:
                results[selector] = {"error": str(e)}
                
        return results

def run_diagnostic():
    """Run comprehensive diagnostic"""
    auth = BostonGlobeDiagnostic()
    
    # Authenticate
    success = auth.authenticate_once("glikfamily@gmail.com", "Eight2Four")
    if not success:
        print("Authentication failed")
        return
        
    # Diagnose page
    test_url = "https://www.bostonglobe.com/2024/11/13/business/"
    print(f"Diagnosing: {test_url}")
    
    result = auth.diagnose_page(test_url)
    
    if result["success"]:
        print(f"\n=== PAGE INFO ===")
        for key, value in result["page_info"].items():
            print(f"{key}: {value}")
            
        print(f"\n=== PAYWALL CHECK ===")
        for key, value in result["paywall_check"].items():
            print(f"{key}: {value}")
            
        print(f"\n=== CONTENT ANALYSIS ===")
        for selector, data in result["content_analysis"].items():
            if "error" not in data:
                print(f"{selector}: {data['element_count']} elements, {data['text_length']} chars")
                if data['text_length'] > 0:
                    print(f"  Preview: {data['preview']}")
            else:
                print(f"{selector}: ERROR - {data['error']}")
                
        print(f"\n=== TOTAL TEXT ===")
        print(f"Length: {result['total_text_length']} chars")
        print(f"Preview: {result['text_preview']}")
        
        print(f"\n=== DEBUG ===")
        print(f"Debug file saved: {result['debug_file']}")
    else:
        print(f"Diagnostic failed: {result['error']}")
        
    auth.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_diagnostic()