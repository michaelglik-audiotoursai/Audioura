# Audio Tours - Docker Container Fix

## Version 1.0.0+79

This update fixes the Docker container issues:

1. **Fixed Missing Module**:
   - Added psycopg2-binary installation to Docker container
   - Restored original tour_orchestrator_service.py file
   - Fixed syntax errors

2. **Database Setup**:
   - Added script to create audio_tours table
   - Added script to check table structure
   - Ensured all necessary columns exist

3. **Simplified Approach**:
   - Removed complex modifications that caused syntax errors
   - Used a simpler approach to fix the issues
   - Provided separate scripts for each task

## How to Deploy

1. Run the restore script to fix the Docker container:
   ```bash
   restore_orchestrator.bat
   ```

2. Set up the database:
   ```bash
   setup_database.bat
   ```

3. Build and install the mobile app:
   ```
   copy ..\pubspec_android_simple.yaml pubspec.yaml
   flutter clean
   flutter pub get
   flutter build apk --release
   ```

## Testing

To test the fix:
1. Generate a tour in the background
2. Wait for it to complete
3. Verify that:
   - The tour is stored in the database
   - You can check with: `SELECT * FROM audio_tours;`

## Troubleshooting

If you still encounter issues:
1. Check the Docker logs:
   ```bash
   docker logs development-tour-orchestrator-1
   ```

2. Check if psycopg2 is installed:
   ```bash
   docker exec -i development-tour-orchestrator-1 pip list | grep psycopg2
   ```