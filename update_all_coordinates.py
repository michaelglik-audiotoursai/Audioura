#!/usr/bin/env python3
"""
Script to add coordinates for all libraries in the database.
This script directly connects to the database and updates coordinates for known libraries.
"""
import psycopg2
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

def update_all_library_coordinates():
    """Update coordinates for all libraries in the database."""
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
        
        # Get all tours
        cur.execute("SELECT id, tour_name, request_string, lat, lng FROM audio_tours")
        tours = cur.fetchall()
        
        print(f"Found {len(tours)} tours in the database")
        
        updated_count = 0
        for tour_id, tour_name, request_string, lat, lng in tours:
            # Skip tours that already have coordinates
            if lat is not None and lng is not None:
                print(f"Tour {tour_id}: '{tour_name}' already has coordinates: lat={lat}, lng={lng}")
                continue
            
            # Try to find coordinates for this tour
            coordinates = None
            
            # Check tour_name and request_string against known libraries
            for name, coords in LIBRARY_COORDINATES.items():
                tour_name_lower = tour_name.lower() if tour_name else ""
                request_string_lower = request_string.lower() if request_string else ""
                
                if name in tour_name_lower or name in request_string_lower:
                    coordinates = coords
                    print(f"Found coordinates for tour {tour_id}: '{tour_name}' using library name '{name}'")
                    break
            
            # If coordinates found, update the tour
            if coordinates:
                lat, lng = coordinates
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
            else:
                print(f"No coordinates found for tour {tour_id}: '{tour_name}'")
        
        # Commit the transaction
        conn.commit()
        
        print(f"\nUpdated {updated_count} tours with coordinates")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error updating library coordinates: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Updating All Library Coordinates =====\n")
    
    success = update_all_library_coordinates()
    
    if success:
        print("\nCoordinates updated successfully!")
    else:
        print("\nFailed to update coordinates")
        sys.exit(1)

if __name__ == "__main__":
    main()