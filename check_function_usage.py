#!/usr/bin/env python3
"""
Script to check if generate_tour_text function is used in other files
"""
import os
import re

def main():
    print("Checking for usage of generate_tour_text function...")
    
    # Directory to search
    search_dir = "."
    
    # Pattern to look for
    pattern = r"generate_tour_text\s*\("
    
    # Files to exclude
    exclude_files = ["modified_generate_tour_text.py", "check_function_usage.py"]
    
    # Track files that use the function
    files_using_function = []
    
    # Walk through all Python files in the directory
    for root, dirs, files in os.walk(search_dir):
        for file in files:
            if file.endswith(".py") and file not in exclude_files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if re.search(pattern, content):
                            files_using_function.append(file_path)
                            print(f"Found usage in: {file_path}")
                            
                            # Extract the line with the function call
                            lines = content.split("\n")
                            for i, line in enumerate(lines):
                                if re.search(pattern, line):
                                    print(f"  Line {i+1}: {line.strip()}")
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    
    if not files_using_function:
        print("No usage of generate_tour_text function found in other Python files.")
    else:
        print(f"\nFound {len(files_using_function)} files using the generate_tour_text function.")
    
    print("Done!")

if __name__ == "__main__":
    main()