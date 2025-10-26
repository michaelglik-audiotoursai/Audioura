"""
Complete audio tour generation script that automates the entire process.
"""
import requests
import json
import time
import os
import zipfile
import subprocess
import sys

def generate_audio_tour(location, tour_type, total_stops):
    """
    Generate a complete audio tour through the entire pipeline.
    
    Args:
        location: Location for the tour
        tour_type: Type of tour (exhibit, park, etc.)
        total_stops: Number of stops in the tour
    """
    print(f"🎯 Generating audio tour for: {location}")
    print(f"📍 Tour type: {tour_type}")
    print(f"🔢 Total stops: {total_stops}")
    print("-" * 60)
    
    try:
        # Step 1: Generate tour text
        print("Step 1/7: Generating tour text...")
        generate_data = {
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops
        }
        
        response = requests.post(
            "http://localhost:5000/generate",
            headers={"Content-Type": "application/json"},
            json=generate_data
        )
        
        if response.status_code != 200:
            print(f"❌ Error generating tour: {response.text}")
            return False
        
        job_data = response.json()
        job_id_1 = job_data["job_id"]
        print(f"✅ Tour generation started (Job ID: {job_id_1})")
        
        # Wait for generation to complete
        print("⏳ Waiting for tour text generation...")
        while True:
            status_response = requests.get(f"http://localhost:5000/status/{job_id_1}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data["status"] == "completed":
                    print("✅ Tour text generation completed!")
                    break
                elif status_data["status"] == "error":
                    print(f"❌ Error in tour generation: {status_data.get('error', 'Unknown error')}")
                    return False
                else:
                    print(f"⏳ Status: {status_data.get('progress', 'Processing...')}")
                    time.sleep(10)
            else:
                print("❌ Error checking status")
                return False
        
        # Step 2: Download tour text file
        print("Step 2/7: Downloading tour text file...")
        # Sanitize filename for Windows compatibility
        safe_location = location.replace(' ', '_').replace(',', '').replace(':', '').replace('/', '_').replace('\\', '_').lower()
        tour_filename = f"{safe_location}_tour.txt"
        
        download_response = requests.get(f"http://localhost:5000/download/{job_id_1}")
        if download_response.status_code == 200:
            with open(tour_filename, 'wb') as f:
                f.write(download_response.content)
            print(f"✅ Downloaded: {tour_filename}")
        else:
            print("❌ Error downloading tour text file")
            return False
        
        # Step 3: Upload to tour processor
        print("Step 3/7: Uploading to tour processor...")
        with open(tour_filename, 'rb') as f:
            files = {'file': f}
            upload_response = requests.post("http://localhost:5001/upload", files=files)
        
        if upload_response.status_code == 200:
            print("✅ File uploaded to tour processor")
        else:
            print(f"❌ Error uploading file: {upload_response.text}")
            return False
        
        # Step 4: Process tour (convert to audio and create HTML)
        print("Step 4/7: Processing tour (text → audio → HTML)...")
        process_data = {"tour_file": tour_filename}
        
        process_response = requests.post(
            "http://localhost:5001/process",
            headers={"Content-Type": "application/json"},
            json=process_data
        )
        
        if process_response.status_code != 200:
            print(f"❌ Error processing tour: {process_response.text}")
            return False
        
        process_job_data = process_response.json()
        job_id_2 = process_job_data["job_id"]
        print(f"✅ Tour processing started (Job ID: {job_id_2})")
        
        # Wait for processing to complete
        print("⏳ Waiting for tour processing (this may take several minutes)...")
        while True:
            status_response = requests.get(f"http://localhost:5001/status/{job_id_2}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data["status"] == "completed":
                    print("✅ Tour processing completed!")
                    break
                elif status_data["status"] == "error":
                    print(f"❌ Error in tour processing: {status_data.get('error', 'Unknown error')}")
                    return False
                else:
                    print(f"⏳ Status: {status_data.get('progress', 'Processing...')}")
                    time.sleep(15)  # Longer wait for audio processing
            else:
                print("❌ Error checking processing status")
                return False
        
        # Step 5: Download Netlify-ready ZIP
        print("Step 5/7: Downloading Netlify deployment package...")
        zip_filename = f"{tour_filename.replace('.txt', '')}_netlify.zip"
        
        download_response = requests.get(f"http://localhost:5001/download/{job_id_2}")
        if download_response.status_code == 200:
            with open(zip_filename, 'wb') as f:
                f.write(download_response.content)
            print(f"✅ Downloaded: {zip_filename}")
        else:
            print("❌ Error downloading Netlify package")
            return False
        
        # Step 6: Extract ZIP file
        print("Step 6/7: Extracting deployment package...")
        # Create safe directory name for Windows
        safe_dir_name = tour_filename.replace('.txt', '').replace(':', '').replace('/', '_').replace('\\', '_')
        extract_dir = f"{safe_dir_name}_netlify"
        
        with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"✅ Extracted to: {extract_dir}")
        
        # Step 7: Start web server
        print("Step 7/7: Starting web server...")
        print(f"🌐 Your audio tour is ready!")
        print(f"📁 Directory: {extract_dir}")
        print(f"🚀 Starting local web server...")
        
        # Change to the extracted directory and start server
        os.chdir(extract_dir)
        
        # Start the web server
        import http.server
        import socketserver
        import socket
        
        # Get local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip_address = s.getsockname()[0]
        except Exception:
            ip_address = '127.0.0.1'
        finally:
            s.close()
        
        # Find an available port starting from 8000
        port = 8000
        max_attempts = 10
        handler = http.server.SimpleHTTPRequestHandler
        
        for attempt in range(max_attempts):
            try:
                httpd = socketserver.TCPServer(("", port), handler)
                break
            except OSError as e:
                if e.errno == 10048:  # Port already in use
                    print(f"⚠️  Port {port} is in use, trying {port + 1}...")
                    port += 1
                    if attempt == max_attempts - 1:
                        print(f"❌ Could not find an available port after trying {max_attempts} ports")
                        print(f"💡 Try closing other web servers or use a different port")
                        return False
                else:
                    raise e
        
        with httpd:
            print(f"\n🎉 SUCCESS! Your audio tour is now running at:")
            print(f"🖥️  Local: http://localhost:{port}")
            print(f"📱 Network: http://{ip_address}:{port}")
            print(f"📂 Serving: {os.getcwd()}")
            print(f"\n💡 Tips:")
            print(f"   • Open the Network URL on your phone to test the tour")
            print(f"   • The tour works completely offline once loaded")
            print(f"   • Deploy the '{extract_dir}' folder to Netlify for public access")
            print(f"\n⏹️  Press Ctrl+C to stop the server")
            print("-" * 60)
            
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n🛑 Server stopped")
                return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to services. Make sure Docker services are running:")
        print("   • Tour generation service (port 5000)")
        print("   • Tour processor service (port 5001)")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python generate_audio_tour.py <location> <tour_type> <total_stops>")
        sys.exit(1)
    
    location = sys.argv[1]
    tour_type = sys.argv[2]
    total_stops = int(sys.argv[3])
    
    generate_audio_tour(location, tour_type, total_stops)     return False

if __name__ == "__main__":
    print("🎵 Audio Tour Generator")
    print("=" * 60)
    
    # Get parameters from command line or user input
    if len(sys.argv) >= 4:
        # Use command line parameters
        location = sys.argv[1]
        tour_type = sys.argv[2]
        total_stops = int(sys.argv[3])
        print(f"📝 Using command line parameters:")
    else:
        # Ask user for parameters
        print("📝 Please provide tour parameters:")
        print()
        
        location = input("🏛️  Enter location (e.g., 'Fruitlands Museum, Harvard, Massachusetts'): ").strip()
        if not location:
            location = "Fruitlands Museum, Harvard, Massachusetts"
            print(f"   Using default: {location}")
        
        tour_type = input("🎯 Enter tour type (e.g., 'exhibit', 'park', 'museum'): ").strip()
        if not tour_type:
            tour_type = "exhibit"
            print(f"   Using default: {tour_type}")
        
        stops_input = input("🔢 Enter number of stops (e.g., 25): ").strip()
        if not stops_input:
            total_stops = 25
            print(f"   Using default: {total_stops}")
        else:
            try:
                total_stops = int(stops_input)
                if total_stops < 1 or total_stops > 50:
                    print("   ⚠️  Number of stops should be between 1 and 50. Using 25.")
                    total_stops = 25
            except ValueError:
                print("   ⚠️  Invalid number. Using default: 25")
                total_stops = 25
        
        print()
        print("📋 Final parameters:")
    
    print(f"   📍 Location: {location}")
    print(f"   🎯 Tour type: {tour_type}")
    print(f"   🔢 Total stops: {total_stops}")
    print("=" * 60)
    
    success = generate_audio_tour(location, tour_type, total_stops)
    
    if not success:
        print("\n❌ Audio tour generation failed!")
        sys.exit(1)
    else:
        print("\n✅ Audio tour generation completed successfully!")