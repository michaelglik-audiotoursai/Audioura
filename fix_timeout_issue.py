#!/usr/bin/env python3
"""
Script to fix timeout issues in tour_orchestrator_service.py
"""
import re

def main():
    print("Adding retry logic and increasing timeouts...")
    
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Add import for socket
    if "import socket" not in content:
        content = content.replace(
            "import requests",
            "import requests\nimport socket"
        )
    
    # Increase timeouts
    content = content.replace("timeout=10", "timeout=30")
    content = content.replace("timeout=60", "timeout=120")
    
    # Add retry logic for the tour generator API call
    pattern = r"(print\(f\"Calling tour generator API: \{datetime\.now\(\)\.isoformat\(\)\}\"\)\s+print\(f\"Request data: \{generate_data\}\"\)\s+)(response = requests\.post\(\s*\"http://tour-generator:5000/generate\",\s*headers=\{\"Content-Type\": \"application/json\"\},\s*json=generate_data,\s*timeout=\d+\s*\))"
    
    replacement = r"""\1# Try with retries
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
            except (requests.exceptions.RequestException, socket.timeout) as e:
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
    
    print("Done! Added retry logic and increased timeouts.")

if __name__ == "__main__":
    main()