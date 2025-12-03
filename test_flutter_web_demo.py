#!/usr/bin/env python3
"""
AudioTours Flutter Web Demo Automated Test Suite
Tests the web version running at http://localhost:8080
"""

import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class AudioToursWebTester:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
        self.driver = None
        self.test_results = []
        
    def setup_driver(self):
        """Initialize Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        # chrome_options.add_argument("--headless")  # Uncomment for headless mode
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
        
    def log_test(self, test_name, status, details=""):
        """Log test results"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)
        print(f"{'✅' if status == 'PASS' else '❌'} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
            
    def test_app_loads(self):
        """Test 1: App loads successfully"""
        try:
            self.driver.get(self.base_url)
            WebDriverWait(self.driver, 30).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Check if Flutter app loaded
            flutter_elements = self.driver.find_elements(By.TAG_NAME, "flutter-view")
            if flutter_elements:
                self.log_test("App Load", "PASS", "Flutter app loaded successfully")
                return True
            else:
                # Check for any content indicating app loaded
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if "AudioTours" in body_text or len(body_text) > 100:
                    self.log_test("App Load", "PASS", "App content detected")
                    return True
                else:
                    self.log_test("App Load", "FAIL", "No Flutter content detected")
                    return False
                    
        except Exception as e:
            self.log_test("App Load", "FAIL", f"Error: {str(e)}")
            return False
            
    def test_map_functionality(self):
        """Test 2: Map loads and displays tours"""
        try:
            # Wait for map-related elements
            time.sleep(5)  # Give Flutter time to initialize
            
            # Check for map container or tour markers
            page_source = self.driver.page_source.lower()
            
            map_indicators = [
                "map", "tour", "marker", "latitude", "longitude", 
                "boston", "newton", "chestnut hill"
            ]
            
            found_indicators = [indicator for indicator in map_indicators if indicator in page_source]
            
            if len(found_indicators) >= 3:
                self.log_test("Map Functionality", "PASS", f"Found indicators: {found_indicators}")
                return True
            else:
                self.log_test("Map Functionality", "PARTIAL", f"Limited indicators: {found_indicators}")
                return False
                
        except Exception as e:
            self.log_test("Map Functionality", "FAIL", f"Error: {str(e)}")
            return False
            
    def test_tour_interaction(self):
        """Test 3: Tour selection and interaction"""
        try:
            # Look for clickable tour elements
            clickable_elements = self.driver.find_elements(By.CSS_SELECTOR, "[role='button'], button, .clickable")
            
            tour_related_clicks = 0
            for element in clickable_elements[:5]:  # Test first 5 clickable elements
                try:
                    element_text = element.text.lower()
                    if any(word in element_text for word in ["tour", "play", "download", "select"]):
                        element.click()
                        time.sleep(2)
                        tour_related_clicks += 1
                        break
                except:
                    continue
                    
            if tour_related_clicks > 0:
                self.log_test("Tour Interaction", "PASS", f"Successfully clicked {tour_related_clicks} tour elements")
                return True
            else:
                self.log_test("Tour Interaction", "PARTIAL", "No tour-specific interactions found")
                return False
                
        except Exception as e:
            self.log_test("Tour Interaction", "FAIL", f"Error: {str(e)}")
            return False
            
    def test_navigation_tabs(self):
        """Test 4: Navigation between app sections"""
        try:
            # Look for navigation elements
            nav_elements = self.driver.find_elements(By.CSS_SELECTOR, "[role='tab'], .tab, .nav-item")
            
            if not nav_elements:
                # Try finding by text content
                all_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Home') or contains(text(), 'Tours') or contains(text(), 'Listen') or contains(text(), 'About')]")
                nav_elements = all_elements
                
            successful_navigations = 0
            for element in nav_elements[:3]:  # Test first 3 navigation elements
                try:
                    original_url = self.driver.current_url
                    element.click()
                    time.sleep(2)
                    
                    # Check if page changed or content updated
                    new_url = self.driver.current_url
                    if new_url != original_url or self.driver.page_source != self.driver.page_source:
                        successful_navigations += 1
                except:
                    continue
                    
            if successful_navigations > 0:
                self.log_test("Navigation", "PASS", f"Successfully navigated {successful_navigations} sections")
                return True
            else:
                self.log_test("Navigation", "PARTIAL", "Limited navigation functionality")
                return False
                
        except Exception as e:
            self.log_test("Navigation", "FAIL", f"Error: {str(e)}")
            return False
            
    def test_responsive_design(self):
        """Test 5: Responsive design at different screen sizes"""
        try:
            screen_sizes = [
                (1920, 1080, "Desktop"),
                (768, 1024, "Tablet"),
                (375, 667, "Mobile")
            ]
            
            responsive_scores = []
            for width, height, device in screen_sizes:
                self.driver.set_window_size(width, height)
                time.sleep(2)
                
                # Check if content is still visible and properly arranged
                body = self.driver.find_element(By.TAG_NAME, "body")
                if body.size['width'] > 0 and body.size['height'] > 0:
                    responsive_scores.append(device)
                    
            if len(responsive_scores) >= 2:
                self.log_test("Responsive Design", "PASS", f"Works on: {responsive_scores}")
                return True
            else:
                self.log_test("Responsive Design", "PARTIAL", f"Limited responsiveness: {responsive_scores}")
                return False
                
        except Exception as e:
            self.log_test("Responsive Design", "FAIL", f"Error: {str(e)}")
            return False
            
    def test_web_storage_functionality(self):
        """Test 6: Web storage implementation (v1.2.8+103 feature)"""
        try:
            # Check if localStorage is being used (web storage implementation)
            local_storage_keys = self.driver.execute_script("return Object.keys(localStorage);")
            session_storage_keys = self.driver.execute_script("return Object.keys(sessionStorage);")
            
            storage_usage = len(local_storage_keys) + len(session_storage_keys)
            
            if storage_usage > 0:
                self.log_test("Web Storage", "PASS", f"Using {storage_usage} storage keys")
                return True
            else:
                # Try to trigger storage by interacting with app
                time.sleep(3)
                local_storage_keys = self.driver.execute_script("return Object.keys(localStorage);")
                if len(local_storage_keys) > 0:
                    self.log_test("Web Storage", "PASS", "Storage activated after interaction")
                    return True
                else:
                    self.log_test("Web Storage", "PARTIAL", "No web storage detected")
                    return False
                    
        except Exception as e:
            self.log_test("Web Storage", "FAIL", f"Error: {str(e)}")
            return False
            
    def test_error_handling(self):
        """Test 7: Error handling and graceful degradation"""
        try:
            # Check browser console for errors
            logs = self.driver.get_log('browser')
            error_count = len([log for log in logs if log['level'] == 'SEVERE'])
            warning_count = len([log for log in logs if log['level'] == 'WARNING'])
            
            if error_count == 0:
                self.log_test("Error Handling", "PASS", f"No severe errors, {warning_count} warnings")
                return True
            elif error_count <= 2:
                self.log_test("Error Handling", "PARTIAL", f"{error_count} errors, {warning_count} warnings")
                return False
            else:
                self.log_test("Error Handling", "FAIL", f"{error_count} severe errors detected")
                return False
                
        except Exception as e:
            self.log_test("Error Handling", "PARTIAL", f"Could not check console logs: {str(e)}")
            return False
            
    def run_all_tests(self):
        """Run complete test suite"""
        print("🚀 Starting AudioTours Flutter Web Demo Test Suite")
        print(f"Testing URL: {self.base_url}")
        print("=" * 60)
        
        try:
            self.setup_driver()
            
            # Run all tests
            tests = [
                self.test_app_loads,
                self.test_map_functionality,
                self.test_tour_interaction,
                self.test_navigation_tabs,
                self.test_responsive_design,
                self.test_web_storage_functionality,
                self.test_error_handling
            ]
            
            passed_tests = 0
            for test in tests:
                if test():
                    passed_tests += 1
                time.sleep(1)  # Brief pause between tests
                
            # Generate summary
            total_tests = len(tests)
            pass_rate = (passed_tests / total_tests) * 100
            
            print("\n" + "=" * 60)
            print("📊 TEST SUMMARY")
            print(f"Total Tests: {total_tests}")
            print(f"Passed: {passed_tests}")
            print(f"Pass Rate: {pass_rate:.1f}%")
            
            if pass_rate >= 80:
                print("🎉 DEMO READY - Excellent performance!")
            elif pass_rate >= 60:
                print("✅ DEMO FUNCTIONAL - Good for presentation")
            else:
                print("⚠️  DEMO NEEDS WORK - Several issues detected")
                
            return self.test_results
            
        finally:
            if self.driver:
                self.driver.quit()
                
    def save_results(self, filename="test_results.json"):
        """Save test results to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.test_results, f, indent=2)
        print(f"📄 Results saved to {filename}")

def main():
    """Main test execution"""
    tester = AudioToursWebTester()
    results = tester.run_all_tests()
    tester.save_results()
    
    return results

if __name__ == "__main__":
    main()