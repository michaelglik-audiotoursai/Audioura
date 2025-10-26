# Audio Tour App - UTC Timestamps & Background Fixes

## Version 1.0.0+73

This version fixes two important issues:

1. **UTC Timestamps**: 
   - All timestamps are now in UTC format
   - Fixes inconsistency between created_at and finished_at
   - Ensures database consistency

2. **Background Tour Monitoring**:
   - Increased check frequency from 30 to 10 seconds
   - More responsive status updates
   - Better handling of background tour generation

### How to Deploy

1. Build and install the mobile app:
   ```
   copy ..\pubspec_android_simple.yaml pubspec.yaml
   flutter clean
   flutter pub get
   flutter build apk --release
   ```

### What Was Fixed

1. **Timezone Issue**:
   - Previously, created_at was in GMT but finished_at was in local time
   - Now all timestamps use DateTime.now().toUtc() for consistency
   - Updated all services to use UTC timestamps

2. **Background Tour Monitoring**:
   - Increased check frequency from 30 to 10 seconds
   - This ensures background tours are monitored more closely
   - Status updates happen more quickly

These changes ensure that all timestamps are consistent and that background tours are properly monitored and updated.