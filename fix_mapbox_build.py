#!/usr/bin/env python3
"""
Script to fix Mapbox build issues in Flutter app
"""
import os
import re

def main():
    print("Fixing Mapbox build issues...")
    
    # Path to the Flutter app
    flutter_app_path = "c:\\Users\\micha\\eclipse-workspace\\AudioTours\\development\\audio_tour_app"
    
    # Check if the Flutter app directory exists
    if not os.path.exists(flutter_app_path):
        print(f"Error: Flutter app directory not found at {flutter_app_path}")
        return
    
    # Path to android/gradle.properties
    gradle_properties_path = os.path.join(flutter_app_path, "android", "gradle.properties")
    
    print(f"Updating {gradle_properties_path}...")
    
    try:
        # Read the current gradle.properties file
        if os.path.exists(gradle_properties_path):
            with open(gradle_properties_path, "r") as f:
                content = f.read()
        else:
            content = ""
        
        # Add Mapbox configuration if not already present
        mapbox_config = """
# Mapbox configuration
MAPBOX_DOWNLOADS_TOKEN=pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpejY4NXVycTA2emYycXBndHRqcmZ3N3gifQ.rJcFIG214AriISLbB6B5aw
"""
        
        if "MAPBOX_DOWNLOADS_TOKEN" not in content:
            content += mapbox_config
            print("Added Mapbox downloads token to gradle.properties")
        else:
            print("Mapbox downloads token already exists in gradle.properties")
        
        # Write the updated file
        with open(gradle_properties_path, "w") as f:
            f.write(content)
        
        print("Successfully updated gradle.properties")
        
    except Exception as e:
        print(f"Error updating gradle.properties: {e}")
    
    # Also check pubspec.yaml for mapbox_gl version
    pubspec_path = os.path.join(flutter_app_path, "pubspec.yaml")
    
    if os.path.exists(pubspec_path):
        print(f"Checking {pubspec_path} for mapbox_gl version...")
        
        try:
            with open(pubspec_path, "r") as f:
                content = f.read()
            
            # Check if mapbox_gl is present and suggest a compatible version
            if "mapbox_gl:" in content:
                print("Found mapbox_gl dependency")
                
                # Check the version
                version_match = re.search(r"mapbox_gl:\s*\^?(\d+\.\d+\.\d+)", content)
                if version_match:
                    version = version_match.group(1)
                    print(f"Current mapbox_gl version: {version}")
                    
                    # Suggest updating to a more stable version if needed
                    if version.startswith("0.16"):
                        print("Consider updating to a more stable version like 0.15.0")
                        print("You can update by changing the version in pubspec.yaml to:")
                        print("  mapbox_gl: ^0.15.0")
            else:
                print("mapbox_gl dependency not found in pubspec.yaml")
        
        except Exception as e:
            print(f"Error reading pubspec.yaml: {e}")
    
    print("\nTo fix the build issue:")
    print("1. The gradle.properties file has been updated with the Mapbox token")
    print("2. Try running 'flutter clean' in the app directory")
    print("3. Then run 'flutter pub get'")
    print("4. Finally, try building again with 'flutter build apk --release'")

if __name__ == "__main__":
    main()