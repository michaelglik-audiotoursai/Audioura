#!/usr/bin/env python3
"""
Script to modify the tour orchestrator service to use the hardcoded coordinates module.
"""
import subprocess
import sys
import time

def modify_tour_orchestrator():
    """Modify the tour orchestrator service to use the hardcoded coordinates module."""
    try:
        # Create the patch content
        patch_content = """
# Add this at the top of the file
import library_coordinates

# Add this to the orchestrate_tour_async function, right after the coordinates = None line
        # Try to get coordinates from hardcoded library coordinates
        library_coords = library_coordinates.get_coordinates(location)
        if library_coords:
            coordinates = library_coords
            print(f"Using hardcoded coordinates for {location}: {coordinates}")
"""
        
        # Write the patch to a temporary file
        with open("tour_orchestrator_patch.txt", "w") as f:
            f.write(patch_content)
        
        print("Created tour_orchestrator_patch.txt")
        
        # Copy the patch to the tour orchestrator container
        result = subprocess.run(
            ["docker", "cp", "tour_orchestrator_patch.txt", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying patch to container: {result.stderr}")
            return False
        
        print("Copied patch to container")
        
        # Create a script to apply the patch
        apply_script = """#!/bin/bash
echo "Applying patch to tour_orchestrator_service.py"
sed -i '1s/^/import library_coordinates\\n/' /app/tour_orchestrator_service.py
sed -i '/coordinates = None/a \\        # Try to get coordinates from hardcoded library coordinates\\n        library_coords = library_coordinates.get_coordinates(location)\\n        if library_coords:\\n            coordinates = library_coords\\n            print(f"Using hardcoded coordinates for {location}: {coordinates}")' /app/tour_orchestrator_service.py
echo "Patch applied"
"""
        
        # Write the apply script to a temporary file
        with open("apply_patch.sh", "w") as f:
            f.write(apply_script)
        
        print("Created apply_patch.sh")
        
        # Copy the apply script to the tour orchestrator container
        result = subprocess.run(
            ["docker", "cp", "apply_patch.sh", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying apply script to container: {result.stderr}")
            return False
        
        print("Copied apply script to container")
        
        # Make the apply script executable
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "chmod", "+x", "/app/apply_patch.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error making apply script executable: {result.stderr}")
            return False
        
        print("Made apply script executable")
        
        # Run the apply script
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "/app/apply_patch.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error applying patch: {result.stderr}")
            return False
        
        print("Applied patch:")
        print(result.stdout)
        
        # Restart the tour orchestrator service
        print("Restarting tour orchestrator service...")
        result = subprocess.run(
            ["docker", "restart", "development-tour-orchestrator-1"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting service: {result.stderr}")
            return False
        
        print("Tour orchestrator service restarted")
        
        # Wait for the service to start
        print("Waiting for service to start...")
        time.sleep(5)
        
        # Check if the service is running
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "ps", "-ef"],
            capture_output=True,
            text=True
        )
        
        if "tour_orchestrator_service.py" not in result.stdout:
            print("WARNING: Tour orchestrator service may not be running")
        else:
            print("Tour orchestrator service is running")
        
        return True
    except Exception as e:
        print(f"Error modifying tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Modifying Tour Orchestrator Service =====\n")
    
    success = modify_tour_orchestrator()
    
    if success:
        print("\nTour orchestrator service modified successfully!")
    else:
        print("\nFailed to modify tour orchestrator service")
        sys.exit(1)

if __name__ == "__main__":
    main()