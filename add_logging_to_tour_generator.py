#!/usr/bin/env python3
"""
Script to add enhanced logging to the tour-generator service
"""
import re

def main():
    print("Adding enhanced logging to tour-generator service...")
    
    # Read the file
    with open("generate_tour_text_service.py", "r") as f:
        content = f.read()
    
    # Add unbuffered logging configuration at the beginning of the file
    imports_end = "from flask_cors import CORS\n"
    unbuffered_config = """from flask_cors import CORS

# Configure unbuffered logging
import sys
import traceback
sys.stdout.reconfigure(line_buffering=True)
print("\\n==== TOUR GENERATOR SERVICE STARTING ====")
print(f"Time: {datetime.now().isoformat()}")
sys.stdout.flush()
"""
    content = content.replace(imports_end, unbuffered_config)
    
    # Add detailed logging to the generate endpoint
    pattern = r"@app\.route\('/generate', methods=\['POST'\]\)\ndef generate_tour_text\(\):"
    replacement = """@app.route('/generate', methods=['POST'])
def generate_tour_text():
    print("\\n==== GENERATE TOUR TEXT REQUEST RECEIVED ====")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Remote address: {request.remote_addr}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data(as_text=True)}")
    print(f"Request JSON: {request.json if request.is_json else None}")
    sys.stdout.flush()"""
    
    content = re.sub(pattern, replacement, content)
    
    # Add try-except block with detailed error logging
    pattern = r"def generate_tour_text\(\):.*?if not request\.is_json:"
    replacement = """def generate_tour_text():
    print("\\n==== GENERATE TOUR TEXT REQUEST RECEIVED ====")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Remote address: {request.remote_addr}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data(as_text=True)}")
    print(f"Request JSON: {request.json if request.is_json else None}")
    sys.stdout.flush()
    
    try:
        if not request.is_json:"""
    
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Add exception handling at the end of the function
    pattern = r"return jsonify\(\{\"job_id\": job_id, \"status\": \"queued\"\}\)"
    replacement = """return jsonify({"job_id": job_id, "status": "queued"})
    except Exception as e:
        print(f"\\n==== EXCEPTION IN GENERATE_TOUR_TEXT: {datetime.now().isoformat()} ====")
        print(f"Exception: {e}")
        print(f"Exception type: {type(e).__name__}")
        print(f"Traceback: {traceback.format_exc()}")
        sys.stdout.flush()
        return jsonify({"error": str(e)}), 500"""
    
    content = re.sub(pattern, replacement, content)
    
    # Write the file
    with open("generate_tour_text_service.py", "w") as f:
        f.write(content)
    
    print("Done! Added enhanced logging to tour-generator service.")

if __name__ == "__main__":
    main()