# Tour Import Tool

This tool imports tour ZIP files from the `tours` directory into the PostgreSQL database.

## Prerequisites

- Python 3.6+
- PostgreSQL database running in Docker (development-postgres-2-1)
- Required Python packages: `psycopg2-binary`, `openai`, `requests`

## How It Works

The tool:

1. Scans the `C:/Users/micha/eclipse-workspace/AudioTours/development/tours` directory for ZIP files matching the pattern `*_tour_netlify_deploy_*.zip`
2. Extracts the request_string from the filename
3. Generates a tour_name by capitalizing words and replacing underscores with spaces
4. Optionally gets geo coordinates using OpenAI API
5. Imports the ZIP file as binary data into the `audio_tours` table

## Usage

### Simple Usage

Run the batch file:

```
import_tours.bat
```

### With OpenAI API Key (for geo coordinates)

```
import_tours.bat --api-key YOUR_OPENAI_API_KEY
```

Or run the Python script directly:

```
python import_tours_to_db.py --api-key YOUR_OPENAI_API_KEY
```

## Database Connection

The tool connects to:
- Host: localhost
- Port: 5433 (mapped to 5432 inside Docker)
- Database: audiotours
- Username: admin
- Password: password123

## Table Structure

The tours are imported into the `audio_tours` table with the following structure:

```sql
CREATE TABLE audio_tours (
    id SERIAL PRIMARY KEY,
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT NOT NULL,
    audio_tour BYTEA,
    number_requested INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION
);
```

## Handling Duplicates

If a tour with the same request_string already exists, the tool will append the unique ID from the filename to the tour_name to make it unique.

## Troubleshooting

- **Database Connection Issues**: Make sure the Docker container is running and the port mapping is correct
- **Missing Packages**: Run `pip install psycopg2-binary openai requests`
- **Permission Issues**: Make sure you have read access to the ZIP files and write access to the database