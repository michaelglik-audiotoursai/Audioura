#!/usr/bin/env python3
"""
Simple script to fix the coordinates service URL in the tour_orchestrator_service.py file
"""
import os

def main():
    # Path to the tour_orchestrator_service.py file
    file_path = "tour_orchestrator_service.py"
    
    # Read the file
    with open(file_path, "r") as f:
        lines = f.readlines()
    
    # Fix the coordinates service URL and timeout
    new_lines = []
    for line in lines:
        if "http://coordinates-fromai:5004/coordinates/" in line:
            line = line.replace("http://coordinates-fromai:5004/coordinates/", "http://coordinates-fromai:5006/coordinates/")
        if "timeout=30" in line:
            line = line.replace("timeout=30", "timeout=60")
        new_lines.append(line)
    
    # Write the file
    with open(file_path, "w") as f:
        f.writelines(new_lines)
    
    print("Fixed coordinates service URL and timeout")

if __name__ == "__main__":
    main()