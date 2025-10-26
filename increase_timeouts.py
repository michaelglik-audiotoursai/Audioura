#!/usr/bin/env python3
"""
Script to increase request timeouts in tour_orchestrator_service.py
"""
import re

def main():
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Increase timeouts
    content = content.replace("timeout=10", "timeout=30")
    content = content.replace("timeout=60", "timeout=120")
    
    # Add retry logic for the initial tour generator request
    pattern = r"response = requests\.post\(\s*\"http://tour-generator:5000/generate\",\s*headers=\{\"Content-Type\": \"application/json\"\},\s*json=generate_data,\s*timeout=\d+\s*\)"
    replacement = """# Try with retries
        max_retries = 3
        retry_count = 0
        while retry_count < max_retries:
            try:
                print(f"Attempt {retry_count + 1}/{max_retries} to call tour generator API")
                response = requests.post(
                    "http://tour-generator:5000/generate",
                    headers={"Content-Type": "application/json"},
                    json=generate_data,
                    timeout=120
                )
                break  # Success, exit the retry loop
            except requests.exceptions.RequestException as e:
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"Failed after {max_retries} attempts: {e}")
                    raise Exception(f"Failed to connect to tour generator after {max_retries} attempts: {e}")
                print(f"Request failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)"""
    
    content = re.sub(pattern, replacement, content)
    
    # Write the file
    with open("tour_orchestrator_service.py", "w") as f:
        f.write(content)
    
    print("Increased timeouts and added retry logic in tour_orchestrator_service.py")

if __name__ == "__main__":
    main()