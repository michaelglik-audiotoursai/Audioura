#!/usr/bin/env python3
"""
Script to update the tour_orchestrator_service.py file with enhanced logging
"""
import os
import re
import sys

def main():
    # Path to the tour_orchestrator_service.py file
    file_path = "tour_orchestrator_service.py"
    
    # Read the file
    with open(file_path, "r") as f:
        content = f.read()
    
    # Add import for enhanced logging
    import_pattern = r"import os\nimport sys\nimport json"
    import_replacement = "import os\nimport sys\nimport json\n\n# Import enhanced logging\nfrom enhanced_logging import logger, log_request, log_response, log_step, log_error, log_api_call, log_api_response, log_job_update"
    content = re.sub(import_pattern, import_replacement, content)
    
    # Replace print statements with logging in orchestrate_tour_async
    content = content.replace("print(f\"\\n==== STEP 1: GENERATING TOUR TEXT ====\\n\")", "log_step(\"GENERATING TOUR TEXT\")")
    content = content.replace("print(f\"Generating tour text for {location} - {tour_type} Tour\")", "logger.info(f\"Generating tour text for {location} - {tour_type} Tour\")")
    content = content.replace("print(f\"Tour text generation completed successfully\")", "logger.info(f\"Tour text generation completed successfully\")")
    content = content.replace("print(f\"ERROR generating tour text: {e}\")", "log_error(e, \"Error generating tour text\")")
    
    # Replace print statements in generate_complete_tour
    content = content.replace("print(\"DEBUG: INCOMING REQUEST FROM MOBILE APP\")", "log_request(request)")
    content = content.replace("print(f\"  Request method: {request.method}\")", "# Logged by log_request")
    content = content.replace("print(f\"  Request headers: {dict(request.headers)}\")", "# Logged by log_request")
    content = content.replace("print(f\"  Request data: {request.get_data(as_text=True)}\")", "# Logged by log_request")
    content = content.replace("print(f\"  Request JSON: {request.json if request.is_json else None}\")", "# Logged by log_request")
    content = content.replace("print(\"==== END OF REQUEST DETAILS ====\\n\")", "# Logged by log_request")
    content = content.replace("print(f\"DEBUG: Received request data: {data}\")", "logger.debug(f\"Received request data: {data}\")")
    
    # Replace print statements in track_user_tour
    content = content.replace("print(f\"DEBUG: Calling user tracking API for user {user_id}\")", "log_api_call(\"user-tracking\", f\"http://user-api-2:5000/user/{user_id}\", \"PUT\", payload)")
    content = content.replace("print(f\"DEBUG: Payload: {payload}\")", "# Logged by log_api_call")
    content = content.replace("print(f\"DEBUG: User tracking response: {response.status_code} - {response.text}\")", "log_api_response(\"user-tracking\", response.status_code, response.text)")
    content = content.replace("print(f\"ERROR: Failed to track user tour: {response.text}\")", "logger.error(f\"Failed to track user tour: {response.text}\")")
    content = content.replace("print(f\"SUCCESS: User tour tracked successfully\")", "logger.info(f\"User tour tracked successfully\")")
    content = content.replace("print(f\"ERROR: Exception tracking user tour: {e}\")", "log_error(e, \"Exception tracking user tour\")")
    
    # Replace print statements in get_coordinates_direct
    content = content.replace("print(f\"\\n==== DIRECT COORDINATES REQUEST FOR: {location} ====\\n\")", "log_api_call(\"coordinates-fromai\", f\"http://coordinates-fromai:5004/coordinates/{encoded_location}\")")
    content = content.replace("print(f\"Requesting URL: {url}\")", "# Logged by log_api_call")
    content = content.replace("print(f\"Response status code: {response.status_code}\")", "log_api_response(\"coordinates-fromai\", response.status_code, data)")
    content = content.replace("print(f\"Received coordinates: lat={lat}, lng={lng}\")", "logger.info(f\"Received coordinates: lat={lat}, lng={lng}\")")
    content = content.replace("print(f\"Invalid response format: {data}\")", "logger.error(f\"Invalid response format: {data}\")")
    content = content.replace("print(f\"Error response: {response.text}\")", "logger.error(f\"Error response: {response.text}\")")
    content = content.replace("print(f\"No coordinates found for {location}\")", "logger.warning(f\"No coordinates found for {location}\")")
    content = content.replace("print(f\"Error getting coordinates from coordinates-fromai service: {e}\")", "log_error(e, \"Error getting coordinates from coordinates-fromai service\")")
    
    # Replace print statements in call_coordinates_service
    content = content.replace("print(f\"\\n==== DIRECT CALL TO COORDINATES-FROMAI SERVICE ====\\n\")", "log_api_call(\"coordinates-fromai\", f\"http://coordinates-fromai:5004/coordinates/{encoded_location}\")")
    content = content.replace("print(f\"Location: {location}\")", "logger.info(f\"Location: {location}\")")
    
    # Replace print statements in main
    content = content.replace("print(f\"Starting Modified Tour Orchestrator Service...\")", "logger.info(\"Starting Modified Tour Orchestrator Service...\")")
    content = content.replace("print(f\"Tours directory: {TOURS_DIR}\")", "logger.info(f\"Tours directory: {TOURS_DIR}\")")
    content = content.replace("print(f\"Pipeline: Complete tour generation orchestration with database storage\")", "logger.info(\"Pipeline: Complete tour generation orchestration with database storage\")")
    
    # Add logging to job status updates
    content = content.replace("ACTIVE_JOBS[job_id][\"status\"] = \"error\"", "ACTIVE_JOBS[job_id][\"status\"] = \"error\"\n        log_job_update(job_id, \"error\", ACTIVE_JOBS[job_id][\"error\"])")
    content = content.replace("ACTIVE_JOBS[job_id][\"status\"] = \"completed\"", "ACTIVE_JOBS[job_id][\"status\"] = \"completed\"\n        log_job_update(job_id, \"completed\", \"Tour generation completed successfully!\")")
    content = content.replace("ACTIVE_JOBS[job_id][\"progress\"] = \"Step", "log_job_update(job_id, ACTIVE_JOBS[job_id][\"status\"], \"Step")
    
    # Fix coordinates service URL
    content = content.replace("http://coordinates-fromai:5004/coordinates/", "http://coordinates-fromai:5006/coordinates/")
    content = content.replace("timeout=30", "timeout=60")
    
    # Write the file
    with open(file_path, "w") as f:
        f.write(content)
    
    print("Updated tour_orchestrator_service.py with enhanced logging")

if __name__ == "__main__":
    main()