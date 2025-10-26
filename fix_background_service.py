"""
Script to fix the background service in the mobile app
"""
import os
import sys
import json
import requests

def update_tour_orchestrator():
    """Update the tour orchestrator service to use the correct database connection"""
    try:
        # Read the current file
        with open('tour_orchestrator_service.py', 'r') as f:
            content = f.read()
        
        # Make a backup
        with open('tour_orchestrator_service.py.bak', 'w') as f:
            f.write(content)
        
        # Replace the database connection
        content = content.replace(
            'host="development-postgres-2-1"',
            'host="postgres-2"'
        )
        
        # Write the updated file
        with open('tour_orchestrator_service.py', 'w') as f:
            f.write(content)
        
        print("Updated tour_orchestrator_service.py")
        return True
    except Exception as e:
        print(f"Error updating tour_orchestrator_service.py: {e}")
        return False

def test_database_connection():
    """Test the database connection"""
    try:
        # Make a request to the tour orchestrator service
        response = requests.get('http://localhost:5002/health')
        if response.status_code == 200:
            print("Tour orchestrator service is running")
            return True
        else:
            print(f"Tour orchestrator service returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error testing database connection: {e}")
        return False

def restart_services():
    """Restart the services"""
    try:
        os.system('docker-compose restart tour-orchestrator')
        print("Restarted tour-orchestrator service")
        return True
    except Exception as e:
        print(f"Error restarting services: {e}")
        return False

if __name__ == "__main__":
    print("Fixing background service...")
    
    # Update the tour orchestrator service
    if update_tour_orchestrator():
        print("Successfully updated tour orchestrator service")
    else:
        print("Failed to update tour orchestrator service")
        sys.exit(1)
    
    # Restart the services
    if restart_services():
        print("Successfully restarted services")
    else:
        print("Failed to restart services")
        sys.exit(1)
    
    # Test the database connection
    if test_database_connection():
        print("Successfully tested database connection")
    else:
        print("Failed to test database connection")
        sys.exit(1)
    
    print("Background service fixed successfully!")