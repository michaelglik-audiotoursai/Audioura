#!/usr/bin/env python3
"""
Script to import tour ZIP files into PostgreSQL database.
This script reads ZIP files from the tours directory and imports them into the audio_tours table.
"""
import os
import re
import sys
import glob
import psycopg2
import requests
import string
from pathlib import Path
import zipfile
import openai
import argparse

# Database connection parameters
DB_PARAMS = {
    "host": "localhost",
    "port": 5433,
    "database": "audiotours",
    "user": "admin",
    "password": "password123"
}

def connect_to_db():
    """Connect to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_tour_name_from_request_string(request_string):
    """
    Convert request_string to tour_name by capitalizing nouns and replacing underscores with spaces.
    """
    # Replace underscores with spaces
    tour_name = request_string.replace('_', ' ')
    
    # Capitalize first letter of each word
    tour_name = string.capwords(tour_name)
    
    return tour_name

def get_geo_coordinates(location_name, api_key):
    """
    Get latitude and longitude for a location using OpenAI API.
    """
    if not api_key:
        print(f"No API key provided, skipping geo coordinates for {location_name}")
        return None, None
    
    try:
        openai.api_key = api_key
        prompt = f"What are the latitude and longitude coordinates for {location_name}? Please respond with only the decimal coordinates in the format: latitude,longitude"
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides geographic coordinates."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50
        )
        
        # Extract coordinates from response
        result = response.choices[0].message.content.strip()
        
        # Try to parse coordinates from various formats
        coord_pattern = r'(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)'
        match = re.search(coord_pattern, result)
        
        if match:
            lat = float(match.group(1))
            lng = float(match.group(2))
            return lat, lng
        else:
            print(f"Could not parse coordinates from response: {result}")
            return None, None
            
    except Exception as e:
        print(f"Error getting coordinates for {location_name}: {e}")
        return None, None

def check_tour_exists(conn, request_string):
    """Check if a tour with the given request_string already exists."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, tour_name FROM audio_tours WHERE request_string = %s", (request_string,))
        return cur.fetchone()

def get_next_id(conn):
    """Get the next ID in the sequence."""
    with conn.cursor() as cur:
        cur.execute("SELECT nextval('audio_tours_id_seq')")
        return cur.fetchone()[0]

def import_tour(conn, zip_path, api_key):
    """Import a tour ZIP file into the database."""
    try:
        # Extract the request_string from the filename
        filename = os.path.basename(zip_path)
        match = re.match(r'(.+)_tour_netlify_deploy_([a-f0-9]+)\.zip', filename)
        
        if not match:
            print(f"Skipping {filename} - doesn't match expected pattern")
            return False
        
        request_string = match.group(1)
        unique_key = match.group(2)
        
        # Check if tour already exists
        existing_tour = check_tour_exists(conn, request_string)
        
        # Generate tour_name
        tour_name = get_tour_name_from_request_string(request_string)
        
        # If tour exists, add unique key to tour_name
        if existing_tour:
            print(f"Tour with request_string '{request_string}' already exists (ID: {existing_tour[0]}, Name: {existing_tour[1]})")
            tour_name = f"{tour_name} (Unique ID: {unique_key})"
        
        # Get geo coordinates
        lat, lng = get_geo_coordinates(request_string.replace('_', ' '), api_key)
        
        # Read the ZIP file as binary data
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
        # Insert into database
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (tour_name, request_string, psycopg2.Binary(zip_data), 0, lat, lng))
            
            tour_id = cur.fetchone()[0]
            conn.commit()
            
            print(f"Successfully imported tour: {tour_name} (ID: {tour_id})")
            return True
            
    except Exception as e:
        conn.rollback()
        print(f"Error importing {zip_path}: {e}")
        return False

def main():
    """Main function to import tours."""
    parser = argparse.ArgumentParser(description='Import tour ZIP files into PostgreSQL database')
    parser.add_argument('--api-key', help='OpenAI API key for geo coordinates')
    args = parser.parse_args()
    
    # Connect to database
    conn = connect_to_db()
    
    # Get all ZIP files in the tours directory
    tours_dir = Path("C:/Users/micha/eclipse-workspace/AudioTours/development/tours")
    zip_files = list(tours_dir.glob("*_tour_netlify_deploy_*.zip"))
    
    print(f"Found {len(zip_files)} tour ZIP files to import")
    
    # Import each tour
    success_count = 0
    for zip_path in zip_files:
        if import_tour(conn, zip_path, args.api_key):
            success_count += 1
    
    print(f"Import complete. Successfully imported {success_count} out of {len(zip_files)} tours.")
    
    # Close connection
    conn.close()

if __name__ == "__main__":
    main()