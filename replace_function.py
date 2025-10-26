#!/usr/bin/env python3
"""
Script to replace the orchestrate_tour_async function in the tour_orchestrator_service.py file
"""
import re

def main():
    # Read the fixed function
    with open("fix_orchestrate_function.py", "r") as f:
        fixed_function = f.read()
    
    # Read the tour_orchestrator_service.py file
    with open("tour_orchestrator_service.py", "r") as f:
        content = f.read()
    
    # Find the orchestrate_tour_async function
    pattern = r"def orchestrate_tour_async\(.*?\)[\s\S]*?(?=\n\n)"
    
    # Replace the function
    new_content = re.sub(pattern, fixed_function, content)
    
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
    
    print("Replaced orchestrate_tour_async function and fixed coordinates service URL")

if __name__ == "__main__":
    main()