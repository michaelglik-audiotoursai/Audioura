"""
Script to fix syntax error in tour_orchestrator_service.py
"""
import os

def fix_syntax_error():
    """Fix the syntax error in tour_orchestrator_service.py"""
    try:
        # Read the original file
        with open('tour_orchestrator_service.py.bak', 'r') as f:
            content = f.read()
        
        # Write the original file back
        with open('tour_orchestrator_service.py', 'w') as f:
            f.write(content)
        
        # Add simple debug logging
        content = content.replace(
            'def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):',
            'def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):\n    print(f"DEBUG: Storing audio tour: {tour_name}, {request_string}, {zip_path}, {lat}, {lng}")'
        )
        
        # Add debug logging for database connection
        content = content.replace(
            'conn = psycopg2.connect(',
            'print("DEBUG: Connecting to database...")\n        conn = psycopg2.connect('
        )
        
        # Add debug logging for database operations
        content = content.replace(
            'if existing_tour:',
            'print(f"DEBUG: Existing tour check result: {existing_tour}")\n        if existing_tour:'
        )
        
        # Write the updated file
        with open('tour_orchestrator_service.py', 'w') as f:
            f.write(content)
        
        print("Fixed syntax error in tour_orchestrator_service.py")
        return True
    except Exception as e:
        print(f"Error fixing syntax error: {e}")
        return False

if __name__ == "__main__":
    fix_syntax_error()