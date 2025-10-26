#!/usr/bin/env python3
"""
Script to clean up any hardcoded coordinates modules from the tour orchestrator container.
"""
import subprocess
import sys

def cleanup_hardcoded_coordinates():
    """Remove any hardcoded coordinates modules from the tour orchestrator container."""
    try:
        print("Removing hardcoded coordinates modules from tour orchestrator container...")
        
        # List of files to remove
        files_to_remove = [
            "/app/library_coordinates.py",
            "/app/test_coordinates_module.py",
            "/app/tour_orchestrator_patch.txt",
            "/app/apply_patch.sh"
        ]
        
        for file_path in files_to_remove:
            # Check if file exists
            result = subprocess.run(
                ["docker", "exec", "development-tour-orchestrator-1", "test", "-f", file_path],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # File exists, remove it
                print(f"Removing {file_path}...")
                subprocess.run(
                    ["docker", "exec", "development-tour-orchestrator-1", "rm", "-f", file_path],
                    capture_output=True,
                    text=True
                )
                print(f"Removed {file_path}")
            else:
                print(f"{file_path} not found, skipping")
        
        print("All hardcoded coordinates modules removed")
        
        return True
    except Exception as e:
        print(f"Error cleaning up hardcoded coordinates: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Cleaning Up Hardcoded Coordinates =====\n")
    
    success = cleanup_hardcoded_coordinates()
    
    if success:
        print("\nCleanup completed successfully!")
    else:
        print("\nCleanup failed")
        sys.exit(1)

if __name__ == "__main__":
    main()