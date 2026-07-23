"""
Fixed version of break_text_to_pois.py that works in current directory
"""
import os
import re

def process_tour_file(tour_file_name):
    """
    Process a tour text file and break it into individual POI files.
    Works in the current directory.
    
    Args:
        tour_file_name: Name of the tour text file to process
    """
    current_dir = os.getcwd()
    print(f"DEBUG: break_text_to_pois working in: {current_dir}")
    print(f"DEBUG: Looking for file: {tour_file_name}")
    
    # Check if file exists in current directory
    if not os.path.exists(tour_file_name):
        raise FileNotFoundError(f"Tour file '{tour_file_name}' not found in {current_dir}")
    
    # Read the tour file
    with open(tour_file_name, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Get directory name from file name (without extension)
    directory_name = os.path.splitext(tour_file_name)[0]
    
    # Create directory for POI files
    if not os.path.exists(directory_name):
        os.makedirs(directory_name)
    
    print(f"DEBUG: Created directory: {directory_name}")
    
    # Split content by "Stop X:" pattern
    stops = re.split(r'\n\s*Stop\s+(\d+):', content)
    
    # Remove the title part (everything before first stop)
    if len(stops) > 1:
        stops = stops[1:]  # Remove title
    
    # Process stops in pairs (number, content)
    stop_number = 1
    for i in range(0, len(stops), 2):
        if i + 1 < len(stops):
            stop_content = f"Stop {stops[i]}:{stops[i+1]}"
        else:
            stop_content = stops[i]
        
        # Clean up the content
        stop_content = stop_content.strip()
        
        if stop_content:
            # Create filename for this stop
            stop_filename = os.path.join(directory_name, f"stop_{stop_number:02d}.txt")
            
            # Write stop content to file
            with open(stop_filename, 'w', encoding='utf-8') as f:
                f.write(stop_content)
            
            print(f"DEBUG: Created {stop_filename}")
            stop_number += 1
    
    print(f"DEBUG: Processed {stop_number - 1} stops")
    return directory_name

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        tour_file = sys.argv[1]
    else:
        tour_file = input("Enter tour file name: ")
    
    process_tour_file(tour_file)