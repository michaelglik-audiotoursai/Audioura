#!/usr/bin/env python3
"""
Script to check the tour generator service
"""
import requests
import json
import time

def main():
    print("=== Testing Tour Generator Service ===")
    
    # Test the health endpoint
    try:
        print("\nTesting health endpoint...")
        response = requests.get("http://tour-generator:5000/health", timeout=10)
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test the generate endpoint
    try:
        print("\nTesting generate endpoint...")
        data = {
            "location": "Test Location, Newton MA",
            "tour_type": "museum",
            "total_stops": 3,
            "include_coordinates": True
        }
        response = requests.post(
            "http://tour-generator:5000/generate",
            headers={"Content-Type": "application/json"},
            json=data,
            timeout=60
        )
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            job_data = response.json()
            job_id = job_data["job_id"]
            print(f"Job ID: {job_id}")
            
            # Poll for job completion
            print("\nPolling for job completion...")
            max_retries = 30
            for i in range(max_retries):
                print(f"Attempt {i+1}/{max_retries}...")
                status_response = requests.get(f"http://tour-generator:5000/status/{job_id}", timeout=10)
                print(f"Status code: {status_response.status_code}")
                print(f"Response: {status_response.text}")
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    if status_data["status"] == "completed":
                        print("Job completed!")
                        
                        # Download the tour text
                        print("\nDownloading tour text...")
                        download_response = requests.get(f"http://tour-generator:5000/download/{job_id}", timeout=60)
                        print(f"Status code: {download_response.status_code}")
                        print(f"Content length: {len(download_response.content)}")
                        
                        # Save the tour text to a file
                        with open("/app/tours/test_tour.txt", "wb") as f:
                            f.write(download_response.content)
                        print("Tour text saved to /app/tours/test_tour.txt")
                        
                        break
                    elif status_data["status"] == "error":
                        print(f"Job failed: {status_data.get('error', 'Unknown error')}")
                        break
                    else:
                        print(f"Job status: {status_data.get('status')}")
                        print(f"Progress: {status_data.get('progress', 'Unknown')}")
                        time.sleep(5)
                else:
                    print(f"Error checking status: {status_response.text}")
                    break
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n=== Done! ===")

if __name__ == "__main__":
    main()