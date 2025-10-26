"""
Simplified app builder for audio tours.
"""
import os
import sys
import shutil
import glob
import zipfile
import webbrowser

# HTML template with doubled curly braces to escape them
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{{{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}}}
        .header {{{{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            text-align: center;
        }}}}
        .tour-container {{{{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}}}
        .tour-item {{{{
            background-color: white;
            border-radius: 8px;
            margin-bottom: 20px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}}}
        .tour-title {{{{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
        }}}}
        audio {{{{
            width: 100%;
        }}}}
        .offline-notice {{{{
            background-color: #4CAF50;
            color: white;
            text-align: center;
            padding: 10px;
            margin-bottom: 20px;
        }}}}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
    </div>
    
    <div class="tour-container">
        <div class="offline-notice">
            This app works offline! Save it to your home screen.
        </div>
        
        {audio_items}
    </div>

    <script>
        // Force cache all audio files
        document.addEventListener('DOMContentLoaded', function() {{{{
            const audioElements = document.querySelectorAll('audio');
            audioElements.forEach(audio => {{{{
                audio.load();
                
                // Pause other audio when one starts playing
                audio.addEventListener('play', function() {{{{
                    audioElements.forEach(other => {{{{
                        if (other !== audio) {{{{
                            other.pause();
                        }}}}
                    }}}});
                }}}});
            }}}});
        }}}});
    </script>
</body>
</html>
"""

def create_simple_app(tour_directory):
    """Create a simple HTML5 app for the tour."""
    # Get absolute paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tour_dir = os.path.join(script_dir, tour_directory)
    
    # Check if tour directory exists
    if not os.path.exists(tour_dir):
        print(f"Error: Tour directory '{tour_directory}' not found")
        return
    
    # Create app directory
    app_dir = os.path.join(script_dir, f"{tour_directory}_app")
    os.makedirs(app_dir, exist_ok=True)
    
    # Find all MP3 files
    mp3_files = glob.glob(os.path.join(tour_dir, "audio_*.mp3"))
    if not mp3_files:
        print(f"Error: No audio files found in {tour_dir}")
        return
    
    print(f"Found {len(mp3_files)} audio files")
    
    # Sort files by stop number
    mp3_files.sort(key=lambda f: int(os.path.basename(f).split('_')[1]))
    
    # Copy each MP3 file
    for mp3_file in mp3_files:
        dest_file = os.path.join(app_dir, os.path.basename(mp3_file))
        shutil.copy2(mp3_file, dest_file)
        print(f"Copied {os.path.basename(mp3_file)}")
    
    # Create HTML file
    title = tour_directory.replace("_", " ").title()
    
    # Generate audio items HTML
    audio_items = ""
    for mp3_file in mp3_files:
        basename = os.path.basename(mp3_file)
        # Extract stop number and name
        parts = basename.replace('.mp3', '').split('_')
        stop_num = parts[1]
        name = ' '.join(parts[2:]).replace('_', ' ').title()
        stop_title = f"Stop {stop_num}: {name}"
        
        audio_items += f"""
        <div class="tour-item">
            <div class="tour-title">{stop_title}</div>
            <audio controls preload="auto">
                <source src="{basename}" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio>
        </div>
        """
    
    # Create HTML file
    html_content = HTML_TEMPLATE.format(title=title, audio_items=audio_items)
    with open(os.path.join(app_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    
    # Create a ZIP file
    zip_path = os.path.join(script_dir, f"{tour_directory}_app.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(app_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, app_dir)
                zipf.write(file_path, arcname)
    
    print(f"\nApp created successfully!")
    print(f"App files are in: {app_dir}")
    print(f"ZIP archive created: {zip_path}")
    
    # Open the app in browser
    index_path = os.path.join(app_dir, "index.html")
    webbrowser.open(f"file://{index_path}")
    
    print("\nTo use on your phone:")
    print("1. Transfer the ZIP file to your phone")
    print("2. Extract the ZIP file")
    print("3. Open index.html in your phone's browser")
    print("4. Add to home screen when prompted")

if __name__ == "__main__":
    # Get tour directory from command line argument or prompt
    if len(sys.argv) > 1:
        tour_dir = sys.argv[1]
    else:
        # List available directories
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dirs = [d for d in os.listdir(script_dir) 
                if os.path.isdir(os.path.join(script_dir, d)) 
                and not d.startswith('.') 
                and not d.startswith('__')
                and d != "mobile_app"]
        
        if not dirs:
            print("No tour directories found.")
            sys.exit(1)
            
        print("Available tour directories:")
        for i, d in enumerate(dirs, 1):
            print(f"{i}. {d}")
            
        try:
            choice = int(input("\nEnter the number of the directory to package (or press Enter for the first one): ") or "1")
            if 1 <= choice <= len(dirs):
                tour_dir = dirs[choice-1]
            else:
                print("Invalid choice. Using the first directory.")
                tour_dir = dirs[0]
        except ValueError:
            print("Invalid input. Using the first directory.")
            tour_dir = dirs[0]
    
    # Create the simple app
    create_simple_app(tour_dir)