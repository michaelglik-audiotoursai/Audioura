#!/usr/bin/env python3
"""
Test script for getting coordinates from OpenAI API.
This script can be run directly on the server to test the coordinates functionality.
"""
import os
import sys
import json
import requests
import re

def get_openai_api_key():
    """Get the OpenAI API key from environment or tour-generator container."""
    # Try environment variable first
    api_key = os.environ.get('OPENAI_API_KEY')
    if api_key:
        print(f"Using OpenAI API key from environment: {api_key[:5]}...{api_key[-5:]}")
        return api_key
    
    # Try to get from tour-generator container
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "development-tour-generator-1", "bash", "-c", "echo $OPENAI_API_KEY"],
            capture_output=True,
            text=True
        )
        api_key = result.stdout.strip()
        
        if api_key:
            print(f"Using OpenAI API key from tour-generator: {api_key[:5]}...{api_key[-5:]}")
            return api_key
    except Exception as e:
        print(f"Error getting API key from tour-generator: {e}")
    
    # If we get here, no API key was found
    print("ERROR: No OpenAI API key found.")
    print("Please provide an API key as an argument: python test_coordinates.py \"Location Name\" YOUR_API_KEY")
    return None

def get_coordinates(location, api_key=None):
    """Get coordinates for a location using OpenAI API."""
    if not api_key:
        api_key = get_openai_api_key()
        if not api_key:
            return None
    
    print(f"\n==== GETTING COORDINATES FOR: {location} ====\n")
    
    # Create a prompt that asks for coordinates
    prompt = f"What are the latitude and longitude coordinates for {location}? Please respond with only the decimal coordinates in the format 'latitude, longitude' without any other text."
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that provides precise geographic coordinates."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    
    print(f"Requesting coordinates from OpenAI API...")
    print(f"Request data: {json.dumps(data)}")
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        print(f"OpenAI API response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            coordinates_text = result["choices"][0]["message"]["content"].strip()
            
            print(f"OpenAI response: {coordinates_text}")
            
            # Try to parse the coordinates
            try:
                # Extract numbers using regex
                numbers = re.findall(r'-?\d+\.\d+', coordinates_text)
                if len(numbers) >= 2:
                    lat = float(numbers[0])
                    lng = float(numbers[1])
                    print(f"Found coordinates: lat={lat}, lng={lng}")
                    return (lat, lng)
                else:
                    # Try comma-separated format
                    parts = coordinates_text.split(",")
                    if len(parts) >= 2:
                        lat = float(parts[0].strip())
                        lng = float(parts[1].strip())
                        print(f"Found coordinates: lat={lat}, lng={lng}")
                        return (lat, lng)
                    else:
                        print(f"Could not parse coordinates from: {coordinates_text}")
            except Exception as e:
                print(f"Error parsing coordinates: {e}")
                print(f"Raw response: {coordinates_text}")
        else:
            print(f"OpenAI API error: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
    
    return None

def test_coordinates_in_db(location, lat, lng):
    """Test storing coordinates in the database."""
    try:
        import psycopg2
        
        # Connect to the database
        conn = psycopg2.connect(
            host="localhost",
            port=5433,  # Mapped from 5432 in Docker
            database="audiotours",
            user="admin",
            password="password123"
        )
        
        # Create cursor
        cur = conn.cursor()
        
        # Create a test tour entry
        tour_name = f"TEST - {location} Tour"
        request_string = f"TEST - {location}"
        
        print(f"\n==== TESTING DATABASE STORAGE ====\n")
        print(f"Tour name: {tour_name}")
        print(f"Request string: {request_string}")
        print(f"Coordinates: lat={lat}, lng={lng}")
        
        # Check if test tour already exists
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name = %s",
            (tour_name,)
        )
        existing_tour = cur.fetchone()
        
        if existing_tour:
            # Update existing tour
            cur.execute(
                """
                UPDATE audio_tours 
                SET lat = %s, lng = %s
                WHERE id = %s
                """,
                (lat, lng, existing_tour[0])
            )
            print(f"Updated existing test tour with ID {existing_tour[0]}")
        else:
            # Insert new tour
            cur.execute(
                """
                INSERT INTO audio_tours (tour_name, request_string, number_requested, lat, lng)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (tour_name, request_string, 0, lat, lng)
            )
            new_id = cur.fetchone()[0]
            print(f"Created new test tour with ID {new_id}")
        
        # Commit the transaction
        conn.commit()
        
        # Verify the coordinates were stored correctly
        cur.execute(
            "SELECT id, tour_name, lat, lng FROM audio_tours WHERE tour_name = %s",
            (tour_name,)
        )
        tour = cur.fetchone()
        
        if tour:
            print(f"Verified in database: ID={tour[0]}, Name={tour[1]}, lat={tour[2]}, lng={tour[3]}")
            if tour[2] == lat and tour[3] == lng:
                print("SUCCESS: Coordinates stored correctly in database!")
            else:
                print(f"ERROR: Coordinates in database ({tour[2]}, {tour[3]}) don't match expected ({lat}, {lng})")
        else:
            print("ERROR: Could not find tour in database after insert/update")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error testing database storage: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python test_coordinates.py \"Location Name\" [openai_api_key]")
        print("Example: python test_coordinates.py \"Simsbury Public Library, Simsbury Center, CT\"")
        sys.exit(1)
    
    location = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Get coordinates
    coords = get_coordinates(location, api_key)
    
    if coords:
        lat, lng = coords
        print(f"\nCoordinates for {location}:")
        print(f"Latitude: {lat}")
        print(f"Longitude: {lng}")
        
        # Test storing in database
        test_coordinates_in_db(location, lat, lng)
    else:
        print(f"\nFailed to get coordinates for {location}")
        sys.exit(1)

if __name__ == "__main__":
    main()