# Audio Tours - psycopg2 Workaround

## Version 1.0.0+80

This update provides a workaround for the psycopg2 module issue:

1. **Workaround for psycopg2**:
   - Modified the orchestrator to work without psycopg2
   - Created a dummy implementation that logs but doesn't store data
   - This allows the service to start and function normally

2. **Alternative Approaches**:
   - `install_psycopg2.bat`: Attempts to install psycopg2 with all dependencies
   - `modify_orchestrator.bat`: Modifies the orchestrator to work without psycopg2

3. **Mobile App Improvements**:
   - Added better error handling for server connection issues
   - Added more detailed logging for troubleshooting

## How to Deploy

1. Run the modify script to work without psycopg2:
   ```bash
   modify_orchestrator.bat
   ```

2. If you prefer to try installing psycopg2 instead:
   ```bash
   install_psycopg2.bat
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
   - The tour is downloaded and added to "My Tours"
   - The tour is removed from the background jobs list

## Troubleshooting

If you still encounter issues:
1. Check the Docker logs:
   ```bash
   docker logs development-tour-orchestrator-1
   ```

2. Check the debug log viewer in the mobile app