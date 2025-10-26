#!/usr/bin/env python3
"""
Script to modify generate_tour_text function to accept total_stops as a parameter
"""
import re

def main():
    print("Modifying generate_tour_text function...")
    
    # Read the file
    with open("modified_generate_tour_text.py", "r") as f:
        content = f.read()
    
    # Create backup
    with open("modified_generate_tour_text.py.bak", "w") as f:
        f.write(content)
    
    # Update the function signature to include total_stops parameter with default value
    old_signature = r"def generate_tour_text\(location, tour_type, output_file=None\):"
    new_signature = "def generate_tour_text(location, tour_type, output_file=None, total_stops=10):"
    content = re.sub(old_signature, new_signature, content)
    
    # Update the function docstring to include total_stops parameter
    old_docstring = r"""    Args:
        location: Location for the tour
        tour_type: Type of tour \(e\.g\., "sculpture", "architecture"\)
        output_file: File to save the tour text \(optional\)
    
    Returns:
        tuple: \(tour_text, output_file, coordinates\)"""
    
    new_docstring = """    Args:
        location: Location for the tour
        tour_type: Type of tour (e.g., "sculpture", "architecture")
        output_file: File to save the tour text (optional)
        total_stops: Number of stops in the tour (default: 10)
    
    Returns:
        tuple: (tour_text, output_file, coordinates)"""
    
    content = re.sub(old_docstring, new_docstring, content)
    
    # Replace the input prompt with the parameter
    old_code = "    # Get number of stops\n    total_stops = int(input(\"How many total stops would you like in the tour? (default: 10): \") or \"10\")"
    new_code = "    # Use the provided total_stops parameter\n    total_stops = int(total_stops)  # Ensure it's an integer"
    content = content.replace(old_code, new_code)
    
    # Write the updated file
    with open("modified_generate_tour_text.py", "w") as f:
        f.write(content)
    
    print("Done! Modified generate_tour_text function to accept total_stops as a parameter.")
    print("A backup of the original file has been created as modified_generate_tour_text.py.bak")

if __name__ == "__main__":
    main()