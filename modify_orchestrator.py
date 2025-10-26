"""
Script to modify tour_orchestrator_service.py to work without psycopg2
"""
import os

def modify_orchestrator():
    """Modify the tour_orchestrator_service.py file to work without psycopg2"""
    try:
        # Read the original file
        with open('tour_orchestrator_service.py', 'r') as f:
            content = f.read()
        
        # Make a backup if it doesn't exist
        if not os.path.exists('tour_orchestrator_service.py.bak'):
            with open('tour_orchestrator_service.py.bak', 'w') as f:
                f.write(content)
        
        # Replace the psycopg2 import with a dummy implementation
        modified_content = content.replace(
            'import psycopg2',
            '''# Dummy implementation for psycopg2
class DummyPsycopg2:
    def Binary(self, data):
        return data

# Create a dummy instance
psycopg2 = DummyPsycopg2()'''
        )
        
        # Replace the store_audio_tour function with a dummy implementation
        modified_content = modified_content.replace(
            'def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):',
            '''def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):
    """Store an audio tour in the database with coordinates and ZIP file."""
    print(f"DEBUG: Would store tour: {tour_name}, {request_string}, {zip_path}, {lat}, {lng}")
    # This is a dummy implementation that doesn't actually store anything
    return True'''
        )
        
        # Remove the function body of store_audio_tour
        start = modified_content.find('def store_audio_tour(')
        end = modified_content.find('def orchestrate_tour_async(')
        function_body = modified_content[start:end]
        
        # Find the end of the function definition line
        function_def_end = function_body.find(':') + 1
        
        # Replace the function body with the dummy implementation
        new_function_body = function_body[:function_def_end] + '''
    """Store an audio tour in the database with coordinates and ZIP file."""
    print(f"DEBUG: Would store tour: {tour_name}, {request_string}, {zip_path}, {lat}, {lng}")
    # This is a dummy implementation that doesn't actually store anything
    return True

'''
        
        modified_content = modified_content.replace(function_body, new_function_body)
        
        # Write the modified file
        with open('tour_orchestrator_service.py', 'w') as f:
            f.write(modified_content)
        
        print("Modified tour_orchestrator_service.py to work without psycopg2")
        return True
    except Exception as e:
        print(f"Error modifying file: {e}")
        return False

if __name__ == "__main__":
    modify_orchestrator()