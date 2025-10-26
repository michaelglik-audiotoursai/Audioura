"""
Script to fix database storage in tour_orchestrator_service.py
"""
import os
import sys
import re

def fix_orchestrator_service():
    """Fix the tour_orchestrator_service.py file"""
    try:
        # Read the current file
        with open('tour_orchestrator_service.py', 'r') as f:
            content = f.read()
        
        # Make a backup
        with open('tour_orchestrator_service.py.bak', 'w') as f:
            f.write(content)
        
        # Add debug logging for database storage
        content = content.replace(
            'def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):',
            'def store_audio_tour(tour_name, request_string, zip_path, lat=None, lng=None):\n    """Store an audio tour in the database with coordinates and ZIP file."""\n    print(f"DEBUG: Storing audio tour: {tour_name}, {request_string}, {zip_path}, {lat}, {lng}")'
        )
        
        # Add more debug logging
        content = content.replace(
            'try:\n        # Read the ZIP file as binary data',
            'try:\n        print("DEBUG: Reading ZIP file...")\n        # Read the ZIP file as binary data'
        )
        
        # Add more debug logging for database connection
        content = content.replace(
            'conn = psycopg2.connect(',
            'print("DEBUG: Connecting to database...")\n        conn = psycopg2.connect('
        )
        
        # Add more debug logging for database operations
        content = content.replace(
            'if existing_tour:',
            'print(f"DEBUG: Existing tour check result: {existing_tour}")\n        if existing_tour:'
        )
        
        # Add more debug logging for database operations
        content = content.replace(
            'conn.commit()',
            'conn.commit()\n        print("DEBUG: Database transaction committed")'
        )
        
        # Add more debug logging for database operations
        content = content.replace(
            'return True',
            'print("DEBUG: Audio tour stored successfully")\n        return True'
        )
        
        # Add more debug logging for database operations
        content = content.replace(
            'print(f"Error storing audio tour: {e}")',
            'print(f"ERROR: Failed to store audio tour: {e}")'
        )
        
        # Add more debug logging for database operations in orchestrate_tour_async
        content = content.replace(
            'store_success = store_audio_tour(tour_name, request_string or location, zip_path, lat, lng)',
            'print(f"DEBUG: Calling store_audio_tour with: {tour_name}, {request_string or location}, {zip_path}, {lat}, {lng}")\n        store_success = store_audio_tour(tour_name, request_string or location, zip_path, lat, lng)'
        )
        
        # Write the updated file
        with open('tour_orchestrator_service.py', 'w') as f:
            f.write(content)
        
        print("Updated tour_orchestrator_service.py with debug logging")
        return True
    except Exception as e:
        print(f"Error updating tour_orchestrator_service.py: {e}")
        return False

def create_audio_tours_table_script():
    """Create a script to create the audio_tours table"""
    try:
        script_content = """
import psycopg2

def create_audio_tours_table():
    try:
        # Connect to the database
        conn = psycopg2.connect(
            host="postgres-2",
            port=5432,
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Check if table exists
        cur.execute(\"\"\"
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'audio_tours'
            )
        \"\"\")
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            print("Creating audio_tours table...")
            cur.execute(\"\"\"
                CREATE TABLE audio_tours (
                    id SERIAL PRIMARY KEY,
                    tour_name TEXT NOT NULL,
                    request_string TEXT NOT NULL,
                    audio_tour BYTEA,
                    number_requested INTEGER NOT NULL DEFAULT 0,
                    lat DOUBLE PRECISION,
                    lng DOUBLE PRECISION
                )
            \"\"\")
            print("Table created successfully")
        else:
            print("audio_tours table already exists")
        
        # Commit the transaction
        conn.commit()
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error creating table: {e}")
        return False

if __name__ == "__main__":
    create_audio_tours_table()
"""
        
        # Write the script
        with open('create_audio_tours_table.py', 'w') as f:
            f.write(script_content)
        
        print("Created create_audio_tours_table.py")
        return True
    except Exception as e:
        print(f"Error creating create_audio_tours_table.py: {e}")
        return False

if __name__ == "__main__":
    print("Fixing database storage...")
    
    # Fix the tour_orchestrator_service.py file
    if fix_orchestrator_service():
        print("Successfully updated tour_orchestrator_service.py")
    else:
        print("Failed to update tour_orchestrator_service.py")
        sys.exit(1)
    
    # Create the create_audio_tours_table.py script
    if create_audio_tours_table_script():
        print("Successfully created create_audio_tours_table.py")
    else:
        print("Failed to create create_audio_tours_table.py")
        sys.exit(1)
    
    print("Database storage fix completed successfully!")