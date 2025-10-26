#!/usr/bin/env python3
"""
Alternative fix for Mapbox issues - replace with a different map plugin
"""
import os
import re

def main():
    print("Alternative fix: Replacing mapbox_gl with flutter_map...")
    
    # Path to the Flutter app
    flutter_app_path = "c:\\Users\\micha\\eclipse-workspace\\AudioTours\\development\\audio_tour_app"
    
    # Check if the Flutter app directory exists
    if not os.path.exists(flutter_app_path):
        print(f"Error: Flutter app directory not found at {flutter_app_path}")
        return
    
    # Path to pubspec.yaml
    pubspec_path = os.path.join(flutter_app_path, "pubspec.yaml")
    
    if not os.path.exists(pubspec_path):
        print(f"Error: pubspec.yaml not found at {pubspec_path}")
        return
    
    print(f"Updating {pubspec_path}...")
    
    try:
        # Read the current pubspec.yaml file
        with open(pubspec_path, "r") as f:
            content = f.read()
        
        # Create backup
        with open(pubspec_path + ".bak", "w") as f:
            f.write(content)
        
        # Replace mapbox_gl with flutter_map
        if "mapbox_gl:" in content:
            # Remove mapbox_gl dependency
            content = re.sub(r"\s*mapbox_gl:.*\n", "", content)
            print("Removed mapbox_gl dependency")
            
            # Add flutter_map dependency if not already present
            if "flutter_map:" not in content:
                # Find the dependencies section and add flutter_map
                dependencies_match = re.search(r"(dependencies:\s*\n)", content)
                if dependencies_match:
                    insert_pos = dependencies_match.end()
                    flutter_map_dep = "  flutter_map: ^6.1.0\n  latlong2: ^0.8.1\n"
                    content = content[:insert_pos] + flutter_map_dep + content[insert_pos:]
                    print("Added flutter_map dependency")
        
        # Write the updated file
        with open(pubspec_path, "w") as f:
            f.write(content)
        
        print("Successfully updated pubspec.yaml")
        print("Note: You'll need to update your Dart code to use flutter_map instead of mapbox_gl")
        
    except Exception as e:
        print(f"Error updating pubspec.yaml: {e}")

if __name__ == "__main__":
    main()