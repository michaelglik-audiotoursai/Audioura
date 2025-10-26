#!/usr/bin/env python3
"""
Script to update coordinates for tours in the database using OpenAI API.
"""
import psycopg2
import sys
import requests
import re
import time

def get_coordinates_from_openai(location, api_key):
    """Get coordinates for a location using OpenAI API."""
    try:
        print(f"Requesting coordinates for '{location}' from OpenAI API...")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Create a prompt that asks for coordinates
        prompt = f"What are the latitude and longitude coordinates for {location}? Please respond with only the decimal coordinates in the format 'latitude, longitude' without any other text."
        
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that provides precise geographic coordinates."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
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
        
        return None
    except Exception as e:
        print(f"Error getting coordinates from OpenAI: {e}")
        return None

def update_tour_coordinates(api_key, tour_id=None, tour_name=None):
    """Update coordinates for tours in the database."""
    try:
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
        
        # Get tours to update
        if tour_id:
            cur.execute(
                "SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE id = %s",
                (tour_id,)
            )
        elif tour_name:
            cur.execute(
                "SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE tour_name = %s",
                (tour_name,)
            )
        else:
            cur.execute(
                "SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE lat IS NULL OR lng IS NULL"
            )
        
        tours = cur.fetchall()
        
        if not tours:
            print("No tours found to update")
            return True
        
        print(f"Found {len(tours)} tours to update")
        
        updated_count = 0
        for tour_id, tour_name, request_string, lat, lng in tours:
            print(f"\nProcessing tour {tour_id}: '{tour_name}'")
            
            # Skip tours that already have coordinates
            if lat is not None and lng is not None:
                print(f"Tour already has coordinates: lat={lat}, lng={lng}")
                continue
            
            # Get location from request_string or tour_name
            location = request_string or tour_name
            
            # Get coordinates from OpenAI
            coords = get_coordinates_from_openai(location, api_key)
            
            if coords:
                lat, lng = coords
                
                # Update the tour
                cur.execute(
                    """
                    UPDATE audio_tours 
                    SET lat = %s, lng = %s
                    WHERE id = %s
                    """,
                    (lat, lng, tour_id)
                )
                
                updated_count += 1
                print(f"Updated tour {tour_id}: '{tour_name}' with coordinates: lat={lat}, lng={lng}")
                
                # Commit after each update
                conn.commit()
                
                # Rate limit to avoid OpenAI API rate limits
                time.sleep(1)
            else:
                print(f"Could not get coordinates for tour {tour_id}: '{tour_name}'")
        
        print(f"\nUpdated {updated_count} tours with coordinates")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error updating tour coordinates: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python update_tour_coordinates.py <openai_api_key> [tour_id|tour_name]")
        print("Example: python update_tour_coordinates.py sk-abcdef123456 \"Keene Public Library, Keene, NH - museum Tour\"")
        sys.exit(1)
    
    api_key = sys.argv[1]
    
    tour_id = None
    tour_name = None
    
    if len(sys.argv) > 2:
        # Check if the argument is a number (tour_id) or a string (tour_name)
        if sys.argv[2].isdigit():
            tour_id = int(sys.argv[2])
        else:
            tour_name = sys.argv[2]
    
    print("\n===== Updating Tour Coordinates =====\n")
    
    success = update_tour_coordinates(api_key, tour_id, tour_name)
    
    if success:
        print("\nTour coordinates updated successfully!")
    else:
        print("\nFailed to update tour coordinates")
        sys.exit(1)

if __name__ == "__main__":
    main()