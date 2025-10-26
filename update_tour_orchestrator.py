#!/usr/bin/env python3
"""
Script to update the tour orchestrator service to use the coordinates_fromAI service.
"""
import subprocess
import sys
import re

def update_tour_orchestrator():
    """Update the tour orchestrator service to use the coordinates_fromAI service."""
    try:
        # Read the new get_coordinates_for_location function
        with open("coordinates_function.py", "r") as f:
            new_function = f.read()
        
        # Get the current tour_orchestrator_service.py file
        print("Getting current tour_orchestrator_service.py...")
        
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Replace the get_coordinates_for_location function
        new_service_py = re.sub(
            r"def get_coordinates_for_location\(location\):.*?return None\n",
            new_function + "\n",
            service_py,
            flags=re.DOTALL
        )
        
        # Write the new service file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_service_py)
        
        print("Updated tour_orchestrator_service.py")
        
        # Restart the tour orchestrator service
        print("Restarting tour orchestrator service...")
        result = subprocess.run(
            ["docker-compose", "restart", "tour-orchestrator"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting service: {result.stderr}")
            return False
        
        print("Tour orchestrator service restarted")
        
        return True
    except Exception as e:
        print(f"Error updating tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Updating Tour Orchestrator Service =====\n")
    
    success = update_tour_orchestrator()
    
    if success:
        print("\nTour orchestrator service updated successfully!")
    else:
        print("\nFailed to update tour orchestrator service")
        sys.exit(1)

if __name__ == "__main__":
    main()