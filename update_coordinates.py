#!/usr/bin/env python3
"""
Script to update coordinates for existing tours in the database.
"""
import psycopg2
import sys

def update_tour_coordinates(tour_name, lat, lng):
    """Update coordinates for a tour in the database."""
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
        
        print(f"Looking for tour: {tour_name}")
        
        # Check if tour exists
        cur.execute(
            "SELECT id, lat, lng FROM audio_tours WHERE tour_name = %s",
            (tour_name,)
        )
        tour = cur.fetchone()
        
        if tour:
            tour_id, current_lat, current_lng = tour
            print(f"Found tour with ID {tour_id}")
            print(f"Current coordinates: lat={current_lat}, lng={current_lng}")
            
            # Update coordinates
            cur.execute(
                """
                UPDATE audio_tours 
                SET lat = %s, lng = %s
                WHERE id = %s
                """,
                (lat, lng, tour_id)
            )
            
            # Commit the transaction
            conn.commit()
            
            print(f"Updated coordinates to: lat={lat}, lng={lng}")
            
            # Verify the update
            cur.execute(
                "SELECT id, tour_name, lat, lng FROM audio_tours WHERE id = %s",
                (tour_id,)
            )
            updated_tour = cur.fetchone()
            
            if updated_tour:
                _, _, updated_lat, updated_lng = updated_tour
                print(f"Verified update: lat={updated_lat}, lng={updated_lng}")
                if updated_lat == lat and updated_lng == lng:
                    print("SUCCESS: Coordinates updated successfully!")
                else:
                    print(f"ERROR: Coordinates in database ({updated_lat}, {updated_lng}) don't match expected ({lat}, {lng})")
            else:
                print("ERROR: Could not find tour after update")
        else:
            print(f"ERROR: Tour not found: {tour_name}")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error updating tour coordinates: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 4:
        print("Usage: python update_coordinates.py \"Tour Name\" latitude longitude")
        print("Example: python update_coordinates.py \"Keene Public Library, Keene, NH - museum Tour\" 42.9336 -72.2781")
        sys.exit(1)
    
    tour_name = sys.argv[1]
    try:
        lat = float(sys.argv[2])
        lng = float(sys.argv[3])
    except ValueError:
        print("ERROR: Latitude and longitude must be valid numbers")
        sys.exit(1)
    
    # Update coordinates
    success = update_tour_coordinates(tour_name, lat, lng)
    
    if success:
        print("\nCoordinates updated successfully!")
    else:
        print("\nFailed to update coordinates")
        sys.exit(1)

if __name__ == "__main__":
    main()