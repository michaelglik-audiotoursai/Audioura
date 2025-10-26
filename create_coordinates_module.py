#!/usr/bin/env python3
"""
Script to create a hardcoded coordinates module in the tour orchestrator container.
This will ensure that coordinates are available even if the OpenAI API is not working.
"""
import subprocess
import sys

# Dictionary of known library coordinates
LIBRARY_COORDINATES = {
    "keene public library": (42.9336, -72.2781),
    "simsbury public library": (41.8762, -72.8082),
    "clapp memorial library": (42.2763, -72.3997),
    "belmont public library": (42.3956, -71.1776),
    "hall memorial library": (41.9037, -72.4616),
    "enfield public library": (41.9959, -72.5903),
    "south windsor public library": (41.8456, -72.5717),
    "westfield athenaeum": (42.1251, -72.7495),
    "norfolk library": (41.9673, -73.1995)
}

def create_coordinates_module():
    """Create a Python module with hardcoded coordinates in the tour orchestrator container."""
    try:
        # Create the module content
        module_content = """#!/usr/bin/env python3
\"\"\"
Hardcoded coordinates for common libraries.
This module is used by the tour orchestrator service to get coordinates for libraries.
\"\"\"

# Dictionary of known library coordinates
LIBRARY_COORDINATES = {
"""
        
        # Add each library to the module
        for name, coords in LIBRARY_COORDINATES.items():
            lat, lng = coords
            module_content += f'    "{name}": ({lat}, {lng}),\n'
        
        # Close the dictionary
        module_content += """}

def get_coordinates(location):
    \"\"\"Get coordinates for a location from the hardcoded dictionary.\"\"\"
    location_lower = location.lower()
    
    # Try direct match first
    if location_lower in LIBRARY_COORDINATES:
        return LIBRARY_COORDINATES[location_lower]
    
    # Try partial match
    for name, coords in LIBRARY_COORDINATES.items():
        if name in location_lower or location_lower in name:
            return coords
    
    return None
"""
        
        # Write the module to a temporary file
        with open("library_coordinates.py", "w") as f:
            f.write(module_content)
        
        print("Created library_coordinates.py")
        
        # Copy the module to the tour orchestrator container
        result = subprocess.run(
            ["docker", "cp", "library_coordinates.py", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying module to container: {result.stderr}")
            return False
        
        print("Copied library_coordinates.py to container")
        
        # Create a simple test script to verify the module works
        test_script = """#!/usr/bin/env python3
import library_coordinates

# Test the module
locations = [
    "Keene Public Library, Keene, NH",
    "Simsbury Public Library, Simsbury Center, CT",
    "Clapp Memorial Library, Belchertown, MA",
    "Unknown Library"
]

print("Testing library_coordinates module:")
for location in locations:
    coords = library_coordinates.get_coordinates(location)
    if coords:
        print(f"  {location}: {coords}")
    else:
        print(f"  {location}: No coordinates found")
"""
        
        # Write the test script to a temporary file
        with open("test_coordinates_module.py", "w") as f:
            f.write(test_script)
        
        print("Created test_coordinates_module.py")
        
        # Copy the test script to the tour orchestrator container
        result = subprocess.run(
            ["docker", "cp", "test_coordinates_module.py", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying test script to container: {result.stderr}")
            return False
        
        print("Copied test_coordinates_module.py to container")
        
        # Run the test script in the container
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "python", "/app/test_coordinates_module.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error running test script: {result.stderr}")
            return False
        
        print("\nTest results:")
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
        
        return True
    except Exception as e:
        print(f"Error creating coordinates module: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Creating Hardcoded Coordinates Module =====\n")
    
    success = create_coordinates_module()
    
    if success:
        print("\nHardcoded coordinates module created and installed successfully!")
    else:
        print("\nFailed to create hardcoded coordinates module")
        sys.exit(1)

if __name__ == "__main__":
    main()