"""
Service-compatible version of text_to_index.py that works with the Docker service
"""
from break_text_to_pois import process_tour_file
from build_mp3 import process_directory
from build_web_page import generate_website
import os

def main(tour_file_name: str):
    """
    Process a tour text file into a complete website with audio files.
    Works in the current directory (tours directory in Docker service).
    
    Args:
        tour_file_name: Name of the tour text file to process
    """
    # Don't change directory - work in current directory (tours directory)
    current_dir = os.getcwd()
    print(f' > Working in directory: {current_dir}')
    
    # Check if file exists
    if not os.path.exists(tour_file_name):
        raise FileNotFoundError(f"Tour file '{tour_file_name}' not found in {current_dir}")
    
    print(' > Starting processing of tour file')
    process_tour_file(tour_file_name)
    print(' > Processed tour into files')
    
    # Get directory name from file name (without extension)
    directory_name = tour_file_name.split('.')[0]
    process_directory(directory_name)
    print(' > Processed files into mp3')
    
    generate_website(directory_name)
    print(' > Generated an index file')
    
    return directory_name

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        tour_file = sys.argv[1]
    else:
        tour_file = 'openaiapi_generated_tour_path_2_for_decordova_sculpture_park.txt'
    
    directory = main(tour_file)
    print(f'Generated directory: {directory}')