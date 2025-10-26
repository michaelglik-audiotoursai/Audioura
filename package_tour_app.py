"""
Package an audio tour as a mobile app.
"""
import os
import sys
import shutil
import glob
import subprocess

def package_tour_as_app(tour_directory):
    """
    Package a tour directory as a mobile app.
    
    Args:
        tour_directory: Path to the tour directory containing audio files
    """
    # Get absolute paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tour_dir = os.path.join(script_dir, tour_directory)
    app_dir = os.path.join(script_dir, "mobile_app")
    
    # Check if tour directory exists
    if not os.path.exists(tour_dir):
        print(f"Error: Tour directory '{tour_directory}' not found")
        return
    
    # Check if mobile_app directory exists
    if not os.path.exists(app_dir):
        print(f"Error: Mobile app directory not found at {app_dir}")
        return
    
    print(f"Packaging tour '{tour_directory}' as a mobile app...")
    
    # Copy all MP3 files from tour directory to app directory
    mp3_files = glob.glob(os.path.join(tour_dir, "audio_*.mp3"))
    if not mp3_files:
        print(f"Error: No audio files found in {tour_dir}")
        return
    
    print(f"Found {len(mp3_files)} audio files")
    
    # Copy each MP3 file
    for mp3_file in mp3_files:
        dest_file = os.path.join(app_dir, os.path.basename(mp3_file))
        shutil.copy2(mp3_file, dest_file)
        print(f"Copied {os.path.basename(mp3_file)}")
    
    # Update app title in buildozer.spec
    buildozer_spec = os.path.join(app_dir, "buildozer.spec")
    if os.path.exists(buildozer_spec):
        with open(buildozer_spec, "r") as f:
            spec_content = f.read()
        
        # Update app title
        title = tour_directory.replace("_", " ").title()
        spec_content = spec_content.replace("title = Audio Tour", f"title = {title}")
        
        # Update package name
        package_name = "audiotour." + tour_directory.lower().replace("_", "")
        spec_content = spec_content.replace("package.name = audiotour", f"package.name = {package_name}")
        
        with open(buildozer_spec, "w") as f:
            f.write(spec_content)
    
    print("\nMobile app package prepared!")
    print(f"App files are in: {app_dir}")
    print("\nTo build the Android APK:")
    print("1. Install buildozer: pip install buildozer")
    print("2. Install required dependencies for buildozer")
    print("3. Navigate to the mobile_app directory")
    print("4. Run: buildozer android debug")
    print("\nThe APK will be created in the bin/ directory")

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
    
    # Package the tour as an app
    package_tour_as_app(tour_dir)