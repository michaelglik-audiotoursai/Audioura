#!/usr/bin/env python3
"""
Simple script to fix the coordinates service URL in the tour_orchestrator_service.py file
"""

def main():
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Replace the coordinates service URL
    content = content.replace(
        "http://coordinates-fromai:5004/coordinates/",
        "http://coordinates-fromai:5006/coordinates/"
    )
    
    # Replace the timeout
    content = content.replace(
        "timeout=30",
        "timeout=60"
    )
    
    # Add more detailed logging
    content = content.replace(
        "print(f\"\\n==== DIRECT COORDINATES REQUEST FOR: {location} ====\\n\")",
        "print(f\"\\n==== DIRECT COORDINATES REQUEST FOR: {location} ====\\n\")\n    print(f\"DEBUG: Time: {datetime.now().isoformat()}\")"
    )
    
    content = content.replace(
        "print(f\"Response status code: {response.status_code}\")",
        "print(f\"Response status code: {response.status_code}\")\n        print(f\"DEBUG: Response time: {datetime.now().isoformat()}\")"
    )
    
    content = content.replace(
        "print(f\"ERROR: Failed to track user tour: {response.text}\")",
        "print(f\"ERROR: Failed to track user tour: {response.text}\")\n            print(f\"DEBUG: Error time: {datetime.now().isoformat()}\")"
    )
    
    content = content.replace(
        "print(f\"ERROR: Exception tracking user tour: {e}\")",
        "print(f\"ERROR: Exception tracking user tour: {e}\")\n        print(f\"DEBUG: Exception details: {str(e)}\")\n        print(f\"DEBUG: Exception time: {datetime.now().isoformat()}\")"
    )
    
    content = content.replace(
        "print(f\"Error getting coordinates from coordinates-fromai service: {e}\")",
        "print(f\"Error getting coordinates from coordinates-fromai service: {e}\")\n        print(f\"DEBUG: Exception details: {str(e)}\")\n        print(f\"DEBUG: Exception time: {datetime.now().isoformat()}\")"
    )
    
    # Add more logging to orchestrate_tour_async
    content = content.replace(
        "def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id, request_string):",
        "def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id, request_string):\n    print(f\"\\n==== STARTING TOUR ORCHESTRATION: {job_id} ====\\n\")\n    print(f\"DEBUG: Start time: {datetime.now().isoformat()}\")\n    print(f\"DEBUG: Parameters: location={location}, tour_type={tour_type}, total_stops={total_stops}, user_id={user_id}, request_string={request_string}\")"
    )
    
    # Add more logging to track_user_tour
    content = content.replace(
        "def track_user_tour(user_id, tour_id, request_string):",
        "def track_user_tour(user_id, tour_id, request_string):\n    print(f\"\\n==== TRACKING USER TOUR: {user_id} / {tour_id} ====\\n\")\n    print(f\"DEBUG: Track time: {datetime.now().isoformat()}\")"
    )
    
    # Write the file
    with open("tour_orchestrator_service.py", "w") as f:
        f.write(content)
    
    print("Fixed coordinates service URL and added more logging")

if __name__ == "__main__":
    main()