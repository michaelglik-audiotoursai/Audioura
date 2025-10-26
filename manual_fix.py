#!/usr/bin/env python3
"""
Script to manually fix the tour_orchestrator_service.py file
"""
import os
import re

def main():
    # Read the fixed function
    with open("direct_fix.py", "r") as f:
        fixed_function = f.read()
    
    # Read the tour_orchestrator_service.py file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Find the orchestrate_tour_async function
    pattern = r"def orchestrate_tour_async\(.*?\):.*?(?=def track_user_tour)"
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        # Replace the function
        new_content = content[:match.start()] + fixed_function + "\n\n" + content[match.end():]
        
        # Also fix the coordinates service URL
        new_content = new_content.replace(
            "http://coordinates-fromai:5004/coordinates/",
            "http://coordinates-fromai:5006/coordinates/"
        )
        
        # Replace the timeout
        new_content = new_content.replace(
            "timeout=30",
            "timeout=60"
        )
        
        # Write the file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_content)
        
        print("Successfully replaced orchestrate_tour_async function and fixed coordinates service URL")
    else:
        print("Could not find orchestrate_tour_async function in the file")

if __name__ == "__main__":
    main()