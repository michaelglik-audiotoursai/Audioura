#!/usr/bin/env python3
"""
Install ffmpeg in the tour editing container for REQ-021 audio format conversion
"""

import subprocess
import sys

def install_ffmpeg():
    """Install ffmpeg using apt-get"""
    try:
        print("Updating package list...")
        subprocess.run(['apt-get', 'update'], check=True)
        
        print("Installing ffmpeg...")
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], check=True)
        
        print("Verifying ffmpeg installation...")
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ ffmpeg installed successfully!")
            print(f"Version: {result.stdout.split()[2]}")
            return True
        else:
            print("❌ ffmpeg installation verification failed")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed: {e}")
        return False
    except FileNotFoundError:
        print("❌ apt-get not found. This script requires a Debian/Ubuntu-based container.")
        return False

if __name__ == "__main__":
    success = install_ffmpeg()
    sys.exit(0 if success else 1)