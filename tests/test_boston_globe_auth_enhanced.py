#!/usr/bin/env python3
"""
Comprehensive Boston Globe Authentication Testing
Tests enhanced authentication system with real credentials
"""
import logging
import json
import time
from boston_globe_auth_enhanced import BostonGlobeAuthenticator
from subscription_article_processor import SubscriptionArticleProcessor

def setup_logging():
    """Setup detailed logging for testing"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('boston_globe_auth_test.log')
        ]
    )

def test_enhanced_authenticator():
    """Test the enhanced Boston Globe authenticator directly"""
    print("=" * 60)
    print("TESTING ENHANCED BOSTON GLOBE AUTHENTICATOR")
    print("=" * 60)
    
    authenticator = BostonGlobeAuthenticator()
    
    # Test credentials (provided by user)
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    # Test with Boston Globe homepage first
    test_urls = [
        "https://www.bostonglobe.com/",
        "https://www.bostonglobe.com/2024/11/13/business/",
        "https://www.bostonglobe.com/2024/11/13/metro/"
    ]
    
    results = []
    
    for i, test_url in enumerate(test_urls, 1):
        print(f"\nTest {i}: {test_url}")
        print("-" * 40)
        
        try:
            result = authenticator.authenticate_and_extract(test_url, credentials)
            
            if result['success']:
                content_length = len(result['content'])
                print(f"✅ SUCCESS: Extracted {content_length} characters")
                print(f"Title: {result.get('title', 'N/A')}")
                print(f"Content preview: {result['content'][:200]}...")
                
                results.append({
                    'url': test_url,
                    'success': True,
                    'content_length': content_length,
                    'title': result.get('title', 'N/A')
                })
            else:
                print(f"❌ FAILED: {result['error']}")
                results.append({
                    'url': test_url,
                    'success': False,
                    'error': result['error']
                })
                
        except Exception as e:
            print(f"❌ EXCEPTION: {str(e)}")
            results.append({
                'url': test_url,
                'success': False,
                'error': str(e)
            })
        
        # Wait between tests to avoid rate limiting
        if i < len(test_urls):
            print("Waiting 5 seconds before next test...")
            time.sleep(5)
    
    return results

def test_subscription_processor_integration():
    """Test the subscription article processor with enhanced authentication"""
    print("\n" + "=" * 60)
    print("TESTING SUBSCRIPTION PROCESSOR INTEGRATION")
    print("=" * 60)
    
    processor = SubscriptionArticleProcessor()
    
    # Test with a Boston Globe article URL
    test_article_url = "https://www.bostonglobe.com/2024/11/13/business/"
    test_content = "This is a test article that requires subscription."
    test_user_id = "test_user_enhanced_auth"
    
    print(f"\nTesting with URL: {test_article_url}")
    print(f"User ID: {test_user_id}")
    
    try:
        # Process article with subscription awareness
        processed_content, subscription_required, subscription_domain = processor.process_article_with_subscription(
            test_article_url, test_content, test_user_id
        )
        
        print(f"\nResults:")
        print(f"Subscription Required: {subscription_required}")
        print(f"Subscription Domain: {subscription_domain}")
        print(f"Processed Content Length: {len(processed_content)} chars")
        print(f"Content Preview: {processed_content[:200]}...")
        
        return {
            'success': True,
            'subscription_required': subscription_required,
            'subscription_domain': subscription_domain,
            'content_length': len(processed_content)
        }
        
    except Exception as e:
        print(f"❌ INTEGRATION TEST FAILED: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def test_credential_storage_and_retrieval():
    """Test credential storage and retrieval system"""
    print("\n" + "=" * 60)
    print("TESTING CREDENTIAL STORAGE AND RETRIEVAL")
    print("=" * 60)
    
    processor = SubscriptionArticleProcessor()
    
    test_user_id = "test_user_enhanced_auth"
    test_domain = "bostonglobe.com"
    
    print(f"Testing credential retrieval for:")
    print(f"User ID: {test_user_id}")
    print(f"Domain: {test_domain}")
    
    try:
        credentials = processor.get_user_credentials(test_user_id, test_domain)
        
        if credentials:
            print(f"✅ SUCCESS: Found credentials")
            print(f"Username: {credentials['username']}")
            print(f"Password: {'*' * len(credentials['password'])}")
            return {
                'success': True,
                'has_credentials': True,
                'username': credentials['username']
            }
        else:
            print(f"⚠️  NO CREDENTIALS: No stored credentials found")
            return {
                'success': True,
                'has_credentials': False
            }
            
    except Exception as e:
        print(f"❌ CREDENTIAL TEST FAILED: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def test_end_to_end_workflow():
    """Test complete end-to-end workflow with real Boston Globe newsletter"""
    print("\n" + "=" * 60)
    print("TESTING END-TO-END WORKFLOW")
    print("=" * 60)
    
    # This would test with a real Boston Globe newsletter that has subscription articles
    # For now, we'll simulate the workflow
    
    processor = SubscriptionArticleProcessor()
    
    # Simulate a Boston Globe article from newsletter processing
    test_scenarios = [
        {
            'url': 'https://www.bostonglobe.com/2024/11/13/business/test-article-1',
            'content': 'This article requires a subscription to read the full content.',
            'user_id': 'test_user_enhanced_auth'
        },
        {
            'url': 'https://www.bostonglobe.com/2024/11/13/metro/test-article-2',
            'content': 'Another subscription article with limited preview content.',
            'user_id': 'test_user_enhanced_auth'
        }
    ]
    
    results = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\nScenario {i}: {scenario['url']}")
        print("-" * 40)
        
        try:
            processed_content, subscription_required, subscription_domain = processor.process_article_with_subscription(
                scenario['url'], scenario['content'], scenario['user_id']
            )
            
            result = {
                'scenario': i,
                'url': scenario['url'],
                'success': True,
                'subscription_required': subscription_required,
                'subscription_domain': subscription_domain,
                'original_length': len(scenario['content']),
                'processed_length': len(processed_content),
                'content_improved': len(processed_content) > len(scenario['content'])
            }
            
            print(f"✅ Processed successfully")
            print(f"Subscription Required: {subscription_required}")
            print(f"Subscription Domain: {subscription_domain}")
            print(f"Content: {len(scenario['content'])} → {len(processed_content)} chars")
            print(f"Content Improved: {result['content_improved']}")
            
            results.append(result)
            
        except Exception as e:
            print(f"❌ Scenario {i} failed: {str(e)}")
            results.append({
                'scenario': i,
                'url': scenario['url'],
                'success': False,
                'error': str(e)
            })
    
    return results

def generate_test_report(authenticator_results, integration_result, credential_result, workflow_results):
    """Generate comprehensive test report"""
    print("\n" + "=" * 60)
    print("COMPREHENSIVE TEST REPORT")
    print("=" * 60)
    
    report = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'authenticator_tests': authenticator_results,
        'integration_test': integration_result,
        'credential_test': credential_result,
        'workflow_tests': workflow_results
    }
    
    # Summary statistics
    auth_success_count = sum(1 for r in authenticator_results if r['success'])
    auth_total = len(authenticator_results)
    
    workflow_success_count = sum(1 for r in workflow_results if r['success'])
    workflow_total = len(workflow_results)
    
    print(f"\n📊 TEST SUMMARY:")
    print(f"Enhanced Authenticator: {auth_success_count}/{auth_total} tests passed")
    print(f"Integration Test: {'✅ PASSED' if integration_result['success'] else '❌ FAILED'}")
    print(f"Credential Test: {'✅ PASSED' if credential_result['success'] else '❌ FAILED'}")
    print(f"Workflow Tests: {workflow_success_count}/{workflow_total} scenarios passed")
    
    overall_success = (
        auth_success_count > 0 and 
        integration_result['success'] and 
        credential_result['success'] and 
        workflow_success_count > 0
    )
    
    print(f"\n🎯 OVERALL RESULT: {'✅ ENHANCED AUTHENTICATION WORKING' if overall_success else '❌ ISSUES DETECTED'}")
    
    # Save detailed report
    try:
        with open('boston_globe_auth_test_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n📄 Detailed report saved to: boston_globe_auth_test_report.json")
    except Exception as e:
        print(f"⚠️  Could not save report: {e}")
    
    return report

def main():
    """Run comprehensive Boston Globe authentication tests"""
    setup_logging()
    
    print("🚀 STARTING COMPREHENSIVE BOSTON GLOBE AUTHENTICATION TESTS")
    print("Testing enhanced authentication system with real credentials")
    print("This may take several minutes due to browser automation...")
    
    try:
        # Test 1: Enhanced authenticator
        authenticator_results = test_enhanced_authenticator()
        
        # Test 2: Integration with subscription processor
        integration_result = test_subscription_processor_integration()
        
        # Test 3: Credential storage and retrieval
        credential_result = test_credential_storage_and_retrieval()
        
        # Test 4: End-to-end workflow
        workflow_results = test_end_to_end_workflow()
        
        # Generate comprehensive report
        report = generate_test_report(
            authenticator_results, 
            integration_result, 
            credential_result, 
            workflow_results
        )
        
        return report
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        logging.error(f"Critical error in main test execution: {e}")
        return None

if __name__ == "__main__":
    main()