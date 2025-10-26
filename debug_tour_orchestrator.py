#!/usr/bin/env python3
"""
Debug script to check connectivity between services
"""
import requests
import time
import sys

def check_service(name, url, timeout=10):
    print(f"Checking {name} at {url}...")
    try:
        start_time = time.time()
        response = requests.get(url, timeout=timeout)
        elapsed = time.time() - start_time
        print(f"  Status: {response.status_code}")
        print(f"  Response time: {elapsed:.2f} seconds")
        print(f"  Response: {response.text[:100]}...")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    print("=== Service Connectivity Check ===")
    
    # Check tour-generator
    check_service("tour-generator", "http://tour-generator:5000/health")
    
    # Check coordinates-fromai
    check_service("coordinates-fromai", "http://coordinates-fromai:5004/health")
    
    # Check tour-processor
    check_service("tour-processor", "http://tour-processor:5001/health")
    
    # Check user-api-2
    check_service("user-api-2", "http://user-api-2:5000/health")
    
    # Check tour-update
    check_service("tour-update", "http://tour-update:5001/health")
    
    # Check map-delivery
    check_service("map-delivery", "http://map-delivery:5005/health")
    
    print("\n=== Testing Coordinates Service ===")
    try:
        location = "Boston, MA"
        print(f"Getting coordinates for: {location}")
        url = f"http://coordinates-fromai:5004/coordinates/{location}"
        response = requests.get(url, timeout=30)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\nDone!")

if __name__ == "__main__":
    main()