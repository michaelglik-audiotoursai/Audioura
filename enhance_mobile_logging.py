#!/usr/bin/env python3
"""
Script to enhance mobile app connection logging
"""

def main():
    print("Enhancing mobile app connection logging...")
    
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Update the generate_complete_tour function to add enhanced logging
    old_function_start = """@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    print(f"\\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data(as_text=True)}")
    print(f"Request JSON: {request.json if request.is_json else None}")"""
    
    new_function_start = """@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    # Generate a complete tour from text to audio to web
    print(f"\\n==== MOBILE APP CONNECTION DETECTED: {datetime.now().isoformat()} ====")
    print(f"Remote address: {request.remote_addr}")
    print(f"User agent: {request.headers.get('User-Agent', 'Unknown')}")
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data(as_text=True)}")
    print(f"Request JSON: {request.json if request.is_json else None}")"""
    
    content = content.replace(old_function_start, new_function_start)
    
    # Add a before_request handler to log all incoming requests
    before_request_handler = """
# Log all incoming requests
@app.before_request
def log_request_info():
    print(f"\\n==== REQUEST RECEIVED: {datetime.now().isoformat()} ====")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote address: {request.remote_addr}")
    print(f"User agent: {request.headers.get('User-Agent', 'Unknown')}")
"""
    
    # Insert the before_request handler after the app initialization
    app_init = "app = Flask(__name__)\nCORS(app)"
    content = content.replace(app_init, app_init + before_request_handler)
    
    # Write the file
    with open("tour_orchestrator_service.py", "w") as f:
        f.write(content)
    
    print("Done! Enhanced mobile app connection logging.")

if __name__ == "__main__":
    main()