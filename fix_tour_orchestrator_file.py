#!/usr/bin/env python3
"""
Script to fix the tour orchestrator service file.
"""
import sys

def fix_tour_orchestrator():
    """Fix the tour orchestrator service file."""
    try:
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak_fix2", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak_fix2")
        
        # Fix the syntax error in the store_audio_tour function
        fixed_service_py = service_py.replace(
            "print(f\"Location: {request_string or tour_name}\") from coordinates-fromai service",
            "print(f\"Location: {request_string or tour_name}\")"
        )
        
        # Write the fixed file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(fixed_service_py)
        
        print("Fixed syntax error in tour_orchestrator_service.py")
        
        return True
    except Exception as e:
        print(f"Error fixing tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Fixing Tour Orchestrator Service File =====\n")
    
    success = fix_tour_orchestrator()
    
    if success:
        print("\nTour orchestrator service file fixed successfully!")
        print("\nNow restart the tour orchestrator service with:")
        print("docker-compose restart tour-orchestrator")
    else:
        print("\nFailed to fix tour orchestrator service file")
        sys.exit(1)

if __name__ == "__main__":
    main()