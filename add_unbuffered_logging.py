#!/usr/bin/env python3
"""
Script to add unbuffered logging to tour_orchestrator_service.py
"""

def main():
    print("Adding unbuffered logging...")
    
    # Read the file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Add unbuffered logging configuration at the beginning of the file
    imports_end = "from flask_cors import CORS\n"
    unbuffered_config = """from flask_cors import CORS

# Configure unbuffered logging
import sys
sys.stdout.reconfigure(line_buffering=True)
"""
    content = content.replace(imports_end, unbuffered_config)
    
    # Add flush calls after key log statements
    content = content.replace(
        'print(f"\\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")',
        'print(f"\\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")\\nsys.stdout.flush()'
    )
    
    content = content.replace(
        'print(f"Generated job ID: {job_id}")',
        'print(f"Generated job ID: {job_id}")\\nsys.stdout.flush()'
    )
    
    content = content.replace(
        'print(f"Starting orchestration in background thread")',
        'print(f"Starting orchestration in background thread")\\nsys.stdout.flush()'
    )
    
    content = content.replace(
        'print(f"Returning response: job_id={job_id}, status=queued")',
        'print(f"Returning response: job_id={job_id}, status=queued")\\nsys.stdout.flush()'
    )
    
    # Write the file
    with open("tour_orchestrator_service.py", "w") as f:
        f.write(content)
    
    print("Done! Added unbuffered logging.")

if __name__ == "__main__":
    main()