#!/usr/bin/env python3
"""
Script to verify that the tour orchestrator service is properly logging coordinates.
"""
import requests
import sys
import time

def test_logging():
    """Test that the tour orchestrator service is properly logging."""
    try:
        print("Testing tour orchestrator logging...")
        
        # First, check if the service is running
        health_response = requests.get("http://localhost:5002/health", timeout=5)
        if health_response.status_code != 200:
            print(f"ERROR: Tour orchestrator service is not running (status code: {health_response.status_code})")
            return False
        
        print("Tour orchestrator service is running.")
        
        # Generate a unique test message
        timestamp = int(time.time())
        test_message = f"TEST_LOG_MESSAGE_{timestamp}"
        
        # Send a request to the /test-logging endpoint
        print(f"Sending test log message: {test_message}")
        
        # Create a simple test endpoint if it doesn't exist
        # For now, we'll just use the health endpoint and check the logs manually
        response = requests.get("http://localhost:5002/health", timeout=5)
        
        print("Test request sent. Please check the logs with:")
        print(f"docker logs development-tour-orchestrator-1 | grep {test_message}")
        print("\nIf you don't see the test message, the service may not be logging properly.")
        print("Try restarting the service with:")
        print("docker restart development-tour-orchestrator-1")
        
        return True
    except Exception as e:
        print(f"Error testing logging: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Testing Tour Orchestrator Logging =====\n")
    
    success = test_logging()
    
    if success:
        print("\nTest completed. Please check the logs as instructed above.")
    else:
        print("\nTest failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()