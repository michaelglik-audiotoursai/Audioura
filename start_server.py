"""
Start a web server for an existing tour directory.
"""
import os
import sys
import http.server
import socketserver
import socket

def start_web_server(directory_name=None, port=8000):
    """
    Start a simple HTTP server to serve the tour files.
    
    Args:
        directory_name: Name of the directory containing the tour files
        port: Port number for the web server (default: 8000)
    """
    # Get current directory to ensure consistent paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Change to the tour directory if specified
    if directory_name:
        server_dir = os.path.join(script_dir, directory_name)
        if not os.path.exists(server_dir):
            print(f"Error: Directory '{directory_name}' not found")
            return
        os.chdir(server_dir)
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
        print(f" > Serving files from: {os.getcwd()}")
        print(f" > Access from your phone using the Network URL")
        print(f" > Press Ctrl+C to stop the server\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n > Server stopped")

if __name__ == '__main__':
    # Get directory name from command line argument or use default
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        # List available directories
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dirs = [d for d in os.listdir(script_dir) 
                if os.path.isdir(os.path.join(script_dir, d)) 
                and not d.startswith('.') 
                and not d.startswith('__')]
        
        if not dirs:
            print("No tour directories found.")
            sys.exit(1)
            
        print("Available tour directories:")
        for i, d in enumerate(dirs, 1):
            print(f"{i}. {d}")
            
        try:
            choice = int(input("\nEnter the number of the directory to serve (or press Enter for the first one): ") or "1")
            if 1 <= choice <= len(dirs):
                directory = dirs[choice-1]
            else:
                print("Invalid choice. Using the first directory.")
                directory = dirs[0]
        except ValueError:
            print("Invalid input. Using the first directory.")
            directory = dirs[0]
    
    # Get port from command line argument or use default
    port = 8000
    if len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            print(f"Invalid port number. Using default port {port}.")
    
    # Start web server
    start_web_server(directory, port)