#!/usr/bin/env python3
"""
Script to add detailed debug logging to the tour_orchestrator_service.py file
"""

def main():
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Add more detailed logging to the orchestrate_tour_async function
    content = content.replace(
        "def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id=None, request_string=None):",
        """def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id=None, request_string=None):
    """Orchestrate the complete tour generation pipeline asynchronously."""
    print(f"\\n==== ORCHESTRATE_TOUR_ASYNC STARTED: {datetime.now().isoformat()} ====")
    print(f"Parameters:")
    print(f"  job_id: {job_id}")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  total_stops: {total_stops}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")"""
    )
    
    # Add more detailed logging to the tour generator API call
    content = content.replace(
        "response = requests.post(",
        """print(f"Calling tour generator API: {datetime.now().isoformat()}")
        print(f"Request data: {generate_data}")
        response = requests.post("""
    )
    
    content = content.replace(
        "if response.status_code != 200:",
        """print(f"Tour generator API response: {response.status_code}")
        print(f"Response content: {response.text[:1000]}")
        if response.status_code != 200:"""
    )
    
    # Add more detailed logging to the status check
    content = content.replace(
        "status_response = requests.get(f\"http://tour-generator:5000/status/{job_id_1}\", timeout=10)",
        """print(f"Checking tour generator status: {datetime.now().isoformat()}")
            status_response = requests.get(f"http://tour-generator:5000/status/{job_id_1}", timeout=10)
            print(f"Status response: {status_response.status_code}")"""
    )
    
    content = content.replace(
        "status_data = status_response.json()",
        """status_data = status_response.json()
                print(f"Status data: {status_data}")"""
    )
    
    # Add exception handling with detailed logging
    content = content.replace(
        "except Exception as e:",
        """except Exception as e:
        import traceback
        print(f"\\n==== EXCEPTION IN ORCHESTRATE_TOUR_ASYNC: {datetime.now().isoformat()} ====")
        print(f"Exception: {e}")
        print(f"Exception type: {type(e).__name__}")
        print(f"Traceback: {traceback.format_exc()}")"""
    )
    
    # Write the file
    with open("tour_orchestrator_service.py", "w") as f:
        f.write(content)
    
    print("Added detailed debug logging to tour_orchestrator_service.py")

if __name__ == "__main__":
    main()