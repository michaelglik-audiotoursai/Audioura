"""
Fixed version of text_to_index.py that works in the current directory for the service
"""
from break_text_to_pois_fixed import process_tour_file
from build_mp3 import process_directory
from build_web_page_fixed import generate_website
import os

def main(tour_file_name: str):
    """
    Process a tour text file into a complete website with audio files.
    Works in the current directory (job working directory).
    
    Args:
        tour_file_name: Name of the tour text file to process
    """
    # Work in current directory - don't change directories
    current_dir = os.getcwd()
    print(f' > Working in directory: {current_dir}')
    print(f' > Processing file: {tour_file_name}')
    
    # Check if file exists in current directory
    if not os.path.exists(tour_file_name):
        raise FileNotFoundError(f"Tour file '{tour_file_name}' not found in {current_dir}")
    
    print(' > Starting processing of tour file')
    process_tour_file(tour_file_name)
    print(' > Processed tour into files')
    
    # Get directory name from file name (without extension)
    directory_name = tour_file_name.rsplit('.', 1)[0]
    process_directory(directory_name)
    print(' > Processed files into mp3')
    
    generate_website(directory_name)
    print(' > Generated an index file')
    
    return directory_name

def start_web_server(directory_name=None, port=8000):
    """
    Start a simple HTTP server to serve the tour files.
    
    Args:
        directory_name: Name of the directory containing the tour files
        port: Port number for the web server (default: 8000)
    """
    import http.server
    import socketserver
    import socket
    
    # Get current directory to ensure consistent paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Change to the tour directory if specified
    if directory_name:
        os.chdir(os.path.join(script_dir, directory_name))
    else:
        os.chdir(script_dir)
    
    # Get local IP address
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = '127.0.0.1'
    finally:
        s.close()
    
    handler = http.server.SimpleHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"\n > Web server started at:")
        print(f" > Local: http://localhost:{port}")
        print(f" > Network: http://{ip_address}:{port}")
        print(f" > Access from your phone using the Network URL")
        print(f" > Press Ctrl+C to stop the server\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n > Server stopped")
    
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        tour_file = sys.argv[1]
    else:
        tour_file = 'openaiapi_generated_tour_path_2_for_decordova_sculpture_park.txt'
    
    directory = main(tour_file)
    
    # Start web server in the tour directory
    start_web_server(directory)