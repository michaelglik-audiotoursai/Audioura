#!/usr/bin/env python3
"""
Script to test connectivity between services
"""
import requests
import time
import sys

def test_service(service_name, url, max_retries=3):
    print(f"Testing connection to {service_name} at {url}")
    
    for i in range(max_retries):
        try:
            print(f"Attempt {i+1}/{max_retries}...")
            start_time = time.time()
            response = requests.get(url, timeout=10)
            end_time = time.time()
            
            print(f"Response time: {end_time - start_time:.2f} seconds")
            print(f"Status code: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            
            return True
        except Exception as e:
            print(f"Error: {e}")
            print(f"Retrying in 2 seconds...")
            time.sleep(2)
    
    print(f"Failed to connect to {service_name} after {max_retries} attempts")
    return False

def main():
    print("=== Testing Service Connectivity ===")
    
    # Test tour-orchestrator
    orchestrator_ok = test_service("tour-orchestrator", "http://localhost:5002/health")
    
    # Test tour-generator
    generator_ok = test_service("tour-generator", "http://tour-generator:5000/health")
    
    # Test tour-processor
    processor_ok = test_service("tour-processor", "http://tour-processor:5001/health")
    
    # Test coordinates-fromai
    coordinates_ok = test_service("coordinates-fromai", "http://coordinates-fromai:5006/health")
    
    print("\n=== Connectivity Summary ===")
    print(f"tour-orchestrator: {'OK' if orchestrator_ok else 'FAILED'}")
    print(f"tour-generator: {'OK' if generator_ok else 'FAILED'}")
    print(f"tour-processor: {'OK' if processor_ok else 'FAILED'}")
    print(f"coordinates-fromai: {'OK' if coordinates_ok else 'FAILED'}")
    
    if not all([orchestrator_ok, generator_ok, processor_ok, coordinates_ok]):
        print("\nSome services are not responding. Please check the Docker containers.")
        sys.exit(1)
    
    print("\nAll services are responding correctly.")

if __name__ == "__main__":
    main()