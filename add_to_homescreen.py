"""
Generate QR code for easy access to audio tour website.
"""
import os
import sys
import socket
import qrcode
from PIL import Image, ImageDraw, ImageFont

def get_local_ip():
    """Get local IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = '127.0.0.1'
    finally:
        s.close()
    return ip_address

def create_qr_code(directory, port=8000):
    """Create QR code for easy access to the tour website."""
    try:
        # Get local IP address
        ip_address = get_local_ip()
        url = f"http://{ip_address}:{port}"
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Add instructions text
        img_with_text = Image.new('RGB', (img.size[0], img.size[1] + 100), color='white')
        img_with_text.paste(img, (0, 0))
        
        draw = ImageDraw.Draw(img_with_text)
        
        # Add text instructions
        instructions = [
            f"1. Scan this QR code with your phone",
            f"2. Open the link in your browser",
            f"3. Add the page to your home screen",
            f"URL: {url}"
        ]
        
        y_position = img.size[1] + 10
        for line in instructions:
            draw.text((10, y_position), line, fill="black")
            y_position += 20
        
        # Save the image
        qr_path = os.path.join(directory, "access_tour.png")
        img_with_text.save(qr_path)
        print(f"QR code created: {qr_path}")
        print(f"Scan this QR code with your phone to access the tour at: {url}")
        
        # Open the image
        try:
            os.startfile(qr_path)  # Windows
        except AttributeError:
            try:
                import subprocess
                subprocess.call(['open', qr_path])  # macOS
            except:
                try:
                    subprocess.call(['xdg-open', qr_path])  # Linux
                except:
                    print(f"Could not open the QR code image. Please open it manually: {qr_path}")
        
        return qr_path
    except ImportError:
        print("qrcode or PIL not installed. Install with: pip install qrcode[pil]")
        return None

if __name__ == "__main__":
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
            choice = int(input("\nEnter the number of the directory (or press Enter for the first one): ") or "1")
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
    
    # Create QR code
    script_dir = os.path.dirname(os.path.abspath(__file__))
    full_dir_path = os.path.join(script_dir, directory)
    create_qr_code(full_dir_path, port)
    
    print("\nInstructions for offline use:")
    print("1. Start the server with: python start_server.py")
    print("2. On your phone, scan the QR code or enter the URL")
    print("3. When the page loads, add it to your home screen:")
    print("   - iOS: tap Share icon, then 'Add to Home Screen'")
    print("   - Android: tap menu (3 dots), then 'Add to Home Screen'")
    print("4. Once added to home screen, the tour will work offline")
    print("   (even when you're away from your WiFi network)")