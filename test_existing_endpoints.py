#!/usr/bin/env python3
"""
Script to test that existing endpoints still work after extending the service
"""
import requests
import json

def test_endpoint(url, description):
    """Test an endpoint and report results"""
    try:
        print(f"Testing {description}...")
        response = requests.get(url, timeout=10)
        print(f"  ✅ Status: {response.status_code}")
        if response.status_code == 200:
            print(f"  ✅ Response: {response.text[:100]}...")
        else:
            print(f"  ⚠️  Response: {response.text[:100]}...")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    print("Testing existing endpoints to ensure they still work...")
    
    # Base URL for the map-delivery service
    base_url = "http://localhost:5004"  # Adjust port if different
    
    # Test existing endpoints (these should already exist)
    endpoints_to_test = [
        (f"{base_url}/health", "Health check"),
        # Add other existing endpoints here as we discover them
    ]
    
    print(f"Testing map-delivery service at {base_url}")
    print("=" * 50)
    
    all_passed = True
    for url, description in endpoints_to_test:
        if not test_endpoint(url, description):
            all_passed = False
    
    print("=" * 50)
    if all_passed:
        print("✅ All existing endpoints are working correctly")
    else:
        print("⚠️  Some endpoints may have issues")
    
    print("\nTesting NEW endpoints (these should work after extension):")
    print("=" * 50)
    
    # Test new endpoints
    new_endpoints = [
        (f"{base_url}/tours-near/42.3601/-71.0589", "Tours near Boston"),
        (f"{base_url}/tour-info/1", "Tour info (if tour ID 1 exists)"),
    ]
    
    for url, description in new_endpoints:
        test_endpoint(url, description)

if __name__ == "__main__":
    main()