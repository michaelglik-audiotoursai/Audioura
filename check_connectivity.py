#!/usr/bin/env python3
"""
Script to check connectivity between services
"""
import requests
import time
import sys

def check_service(name, url, timeout=5):
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
    print("=== Checking service connectivity ===")
    
    services = [
        ("tour-generator", "http://tour-generator:5000/health"),
        ("tour-processor", "http://tour-processor:5001/health"),
        ("coordinates-fromai", "http://coordinates-fromai:5006/health")
    ]
    
    results = {}
    for name, url in services:
        results[name] = check_service(name, url)
    
    print("\n=== Results ===")
    all_ok = True
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"{name}: {status}")
        if not success:
            all_ok = False
    
    if all_ok:
        print("\nAll services are reachable.")
    else:
        print("\nSome services are not reachable. Check Docker container status.")
        print("Try restarting the services:")
        print("  docker-compose restart")

if __name__ == "__main__":
    main()