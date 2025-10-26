#!/usr/bin/env python3
"""
Script to update the version number in the pubspec files.
"""
import sys

def update_version(new_version):
    """Update the version number in the pubspec files."""
    try:
        # Update the main pubspec.yaml file
        with open("audio_tour_app/pubspec.yaml", "r") as f:
            pubspec = f.read()
        
        # Replace the version number
        import re
        new_pubspec = re.sub(
            r"version: \d+\.\d+\.\d+\+\d+",
            f"version: {new_version}",
            pubspec
        )
        
        # Write the new pubspec file
        with open("audio_tour_app/pubspec.yaml", "w") as f:
            f.write(new_pubspec)
        
        print(f"Updated audio_tour_app/pubspec.yaml to version {new_version}")
        
        # Update the Android-specific pubspec.yaml file
        with open("pubspec_android_simple.yaml", "r") as f:
            pubspec = f.read()
        
        # Replace the version number
        new_pubspec = re.sub(
            r"version: \d+\.\d+\.\d+\+\d+",
            f"version: {new_version}",
            pubspec
        )
        
        # Write the new pubspec file
        with open("pubspec_android_simple.yaml", "w") as f:
            f.write(new_pubspec)
        
        print(f"Updated pubspec_android_simple.yaml to version {new_version}")
        
        return True
    except Exception as e:
        print(f"Error updating version: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python update_version.py <new_version>")
        print("Example: python update_version.py 1.0.0+91")
        sys.exit(1)
    
    new_version = sys.argv[1]
    
    print(f"\n===== Updating Version to {new_version} =====\n")
    
    success = update_version(new_version)
    
    if success:
        print(f"\nVersion updated to {new_version} successfully!")
    else:
        print("\nFailed to update version")
        sys.exit(1)

if __name__ == "__main__":
    main()