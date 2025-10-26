# Audio Tours with Coordinates and Database Storage

This update adds two important features to the Audio Tours system:

1. **Geo Coordinates for Tours**: The system now generates and stores geo coordinates for the first POI in each tour
2. **Database Storage of Audio Tours**: Complete audio tours (ZIP files) are now stored in the PostgreSQL database

## New Files

- `store_audio_tours.py`: Script to store audio tours in the database
- `modified_generate_tour_text.py`: Modified version of generate_tour_text.py that includes geo coordinates
- `modified_tour_orchestrator_service.py`: Modified orchestrator that stores tours in the database
- `modified_generate_tour_text_service.py`: Modified text generator service that includes coordinates
- `update_audio_tours_table.sql`: SQL script to update the existing audio_tours table
- `update_db_tables.bat`: Batch script to run the SQL update script

## How It Works

### Geo Coordinates Generation

1. The modified tour text generator now specifically requests geo coordinates from OpenAI for the first POI
2. If OpenAI doesn't provide coordinates in the initial response, a second request is made specifically for coordinates
3. The coordinates are passed through the entire pipeline and stored in the database

### Database Storage

1. When a tour is completed, the ZIP file is stored in the `audio_tours` table
2. The table is updated with new columns if they don't exist:
   - `audio_tour`: Binary data of the ZIP file
   - `number_requested`: Counter for how many times this tour has been requested
   - `lat`: Latitude of the first POI
   - `lng`: Longitude of the first POI

## How to Use

### Updating the Database

1. Run the update script to add the new columns to the existing table:
   ```bash
   update_db_tables.bat
   ```

### Running the Modified Services

1. Replace the existing services with the modified versions:
   ```bash
   update_services.bat
   ```

### Storing Tours Manually

You can also store tours manually using the `store_audio_tours.py` script:

```bash
python store_audio_tours.py --name "Tour Name" --request "Original request" --zip "/path/to/tour.zip" --lat 42.3601 --lng -71.0589
```

## API Changes

### Tour Generator API

The `/status/<job_id>` endpoint now includes coordinates in the response:

```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "completed",
  "progress": "Tour text generation completed successfully!",
  "location": "Boston Public Library",
  "tour_type": "architecture",
  "total_stops": 10,
  "created_at": "2025-07-18T12:34:56.789Z",
  "output_file": "boston_public_library_architecture_tour_20250718_123456.txt",
  "coordinates": [42.3601, -71.0589]
}
```

### Tour Orchestrator API

The `/status/<job_id>` and `/serve/<job_id>` endpoints now include coordinates in the response:

```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "completed",
  "progress": "Tour generation completed successfully!",
  "location": "Boston Public Library",
  "tour_type": "architecture",
  "total_stops": 10,
  "created_at": "2025-07-18T12:34:56.789Z",
  "output_zip": "boston_public_library_architecture_tour_netlify.zip",
  "extract_dir": "boston_public_library_architecture_tour_netlify",
  "netlify_ready": true,
  "coordinates": [42.3601, -71.0589]
}
```

## Benefits

1. **Geo-Enabled Tours**: Tours can now be displayed on maps and integrated with mapping applications
2. **Efficient Storage**: Tours are stored in the database for easy retrieval and management
3. **Usage Tracking**: The system tracks how many times each tour has been requested
4. **Improved User Experience**: Users can see where tours are located on a map