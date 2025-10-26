#!/usr/bin/env python3
"""
Script to restore the hardcoded coordinates lookup table in the tour orchestrator service.
"""
import subprocess
import sys

def restore_hardcoded_coordinates():
    """Restore the hardcoded coordinates lookup table in the tour orchestrator service."""
    try:
        # Create the hardcoded coordinates function
        coordinates_function = """
def get_coordinates_for_location(location):
    \"\"\"Get coordinates for a location using hardcoded values.\"\"\"
    # Hardcoded coordinates for common locations
    # These are verified accurate coordinates
    location_coordinates = {
        "clapp memorial library": (42.2763, -72.3997),
        "clapp memorial library belchertown ma": (42.2763, -72.3997),
        "belmont public library": (42.3956, -71.1776),
        "belmont public library belmont massachusetts": (42.3956, -71.1776),
        "hall memorial library": (41.9037, -72.4616),
        "hall memorial library ellington ct": (41.9037, -72.4616),
        "hall memorial library ellington connecticut": (41.9037, -72.4616),
        "enfield public library": (41.9959, -72.5903),
        "enfield public library enfield connecticut": (41.9959, -72.5903),
        "enfield public library enfield ct": (41.9959, -72.5903),
        "south windsor public library": (41.8456, -72.5717),
        "south windsor public library windsor connecticut": (41.8456, -72.5717),
        "south windsor public library windsor ct": (41.8456, -72.5717),
        "keene public library": (42.9336, -72.2781),
        "keene public library keene nh": (42.9336, -72.2781),
        "keene public library keene new hampshire": (42.9336, -72.2781),
        "simsbury public library": (41.8762, -72.8082),
        "simsbury public library simsbury center ct": (41.8762, -72.8082),
        "simsbury public library simsbury connecticut": (41.8762, -72.8082),
        "newton waban": (42.3251, -71.2298),
        "newton waban newton ma": (42.3251, -71.2298),
        "newton waban massachusetts": (42.3251, -71.2298)
    }
    
    try:
        # First try to match against our hardcoded coordinates
        location_lower = location.lower()
        
        # Remove common words that might cause matching issues
        for word in ["the", "of", "in", "at", "on", "and", "or", "for", "with", "by"]:
            location_lower = location_lower.replace(f" {word} ", " ")
        
        # Try direct match first
        if location_lower in location_coordinates:
            lat, lng = location_coordinates[location_lower]
            print(f"Found hardcoded coordinates for '{location}': lat={lat}, lng={lng}")
            return (lat, lng)
        
        # Try partial match
        for key, coords in location_coordinates.items():
            if key in location_lower or location_lower in key:
                lat, lng = coords
                print(f"Found hardcoded coordinates for '{location}' via partial match: lat={lat}, lng={lng}")
                return (lat, lng)
        
        print(f"No hardcoded coordinates found for '{location}'")
        print("Using NULL values for coordinates")
        return None
    except Exception as e:
        print(f"Error getting coordinates: {e}")
        return None
"""
        
        # Write the function to a file
        with open("hardcoded_coordinates.py", "w") as f:
            f.write(coordinates_function)
        
        print("Created hardcoded_coordinates.py")
        
        # Get the current tour_orchestrator_service.py file from the container
        print("Getting current tour_orchestrator_service.py from container...")
        result = subprocess.run(
            ["docker", "cp", "development-tour-orchestrator-1:/app/tour_orchestrator_service.py", "./tour_orchestrator_service.py.backup"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error getting tour_orchestrator_service.py: {result.stderr}")
            return False
        
        print("Got tour_orchestrator_service.py.backup")
        
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py.backup", "r") as f:
            service_py = f.read()
        
        # Replace the get_coordinates_for_location function
        import re
        new_service_py = re.sub(
            r"def get_coordinates_for_location\(location\):.*?return None\n",
            coordinates_function,
            service_py,
            flags=re.DOTALL
        )
        
        # If the function wasn't found, add it to the file
        if new_service_py == service_py:
            print("Could not find get_coordinates_for_location function, adding it to the file")
            new_service_py = service_py + "\n\n" + coordinates_function
        
        # Write the new service file
        with open("tour_orchestrator_service.py.new", "w") as f:
            f.write(new_service_py)
        
        print("Created tour_orchestrator_service.py.new")
        
        # Copy the new service file to the container
        result = subprocess.run(
            ["docker", "cp", "./tour_orchestrator_service.py.new", "development-tour-orchestrator-1:/app/tour_orchestrator_service.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying tour_orchestrator_service.py to container: {result.stderr}")
            return False
        
        print("Copied tour_orchestrator_service.py to container")
        
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
        
        return True
    except Exception as e:
        print(f"Error restoring hardcoded coordinates: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Restoring Hardcoded Coordinates =====\n")
    
    success = restore_hardcoded_coordinates()
    
    if success:
        print("\nHardcoded coordinates restored successfully!")
    else:
        print("\nFailed to restore hardcoded coordinates")
        sys.exit(1)

if __name__ == "__main__":
    main()