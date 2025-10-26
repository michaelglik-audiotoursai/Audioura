#!/usr/bin/env python3
"""
Script to update generate_tour_text_service.py to pass total_stops to generate_tour_text
"""
import re

def main():
    print("Updating generate_tour_text_service.py...")
    
    try:
        # Read the file
        with open("generate_tour_text_service.py", "r") as f:
            content = f.read()
        
        # Create backup
        with open("generate_tour_text_service.py.bak", "w") as f:
            f.write(content)
        
        # Find the call to generate_tour_text and update it to pass total_stops
        pattern = r"tour_text, output_file, coordinates = generate_tour_text\(location, tour_type(?:, output_file)?\)"
        replacement = "tour_text, output_file, coordinates = generate_tour_text(location, tour_type, output_file, total_stops)"
        
        # Check if the pattern exists
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            print("Updated generate_tour_text call to pass total_stops parameter.")
        else:
            print("Could not find the generate_tour_text call pattern. Please check the file manually.")
            
            # Try to find any call to generate_tour_text
            calls = re.findall(r"generate_tour_text\(.*?\)", content)
            if calls:
                print("Found these calls to generate_tour_text:")
                for call in calls:
                    print(f"  {call}")
        
        # Write the updated file
        with open("generate_tour_text_service.py", "w") as f:
            f.write(content)
        
        print("Done! Updated generate_tour_text_service.py")
        print("A backup of the original file has been created as generate_tour_text_service.py.bak")
    
    except FileNotFoundError:
        print("Error: generate_tour_text_service.py not found.")
        print("Please make sure you're running this script from the directory containing generate_tour_text_service.py")

if __name__ == "__main__":
    main()