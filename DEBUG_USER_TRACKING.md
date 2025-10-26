# Debug User Tracking - Version 0.0.0.3

## Debug APK Ready
**Location**: `build\app\outputs\flutter-apk\app-debug.apk`
**Version**: 0.0.0.3 with enhanced logging

## How to Debug User Tracking

### 1. Install Debug APK
```bash
adb install build\app\outputs\flutter-apk\app-debug.apk
```

### 2. Monitor App Logs
```bash
adb logcat -s flutter
```

### 3. Monitor User Database
```bash
python monitor_user_tracking.py
```

### 4. Generate Tour and Watch Logs

When you generate a tour, you should see:

**Flutter App Logs:**
```
=== USER TRACKING DEBUG ===
User ID: txzs7duahw03g810
Request String: Please generate a walking audio tour for Museum of Ice Cream, Boston, MA
Full Request Data: {"location":"Museum of Ice Cream, Boston, MA","tour_type":"walking","total_stops":10,"user_id":"txzs7duahw03g810","request_string":"Please generate a walking audio tour for Museum of Ice Cream, Boston, MA"}
API URL: http://192.168.0.217:5002/generate-complete-tour
========================
=== TOUR REQUEST RESPONSE ===
Status Code: 200
Response Body: {"job_id":"abc123","status":"queued"}
============================
```

**Expected Database Result:**
- User `txzs7duahw03g810` should appear in database
- Tour request should be recorded immediately
- No need to wait for tour completion

## Troubleshooting Steps

### If User ID is null/empty:
- Check SharedPreferences initialization
- Verify user registration with tracking service

### If API call fails:
- Check network connectivity to 192.168.0.217:5002
- Verify tour orchestrator service is running

### If user not in database:
- Check orchestrator logs: `docker logs development-tour-orchestrator-1`
- Verify network connectivity between orchestrator and user service
- Test direct API call to user service

## Current Known Issues
1. ❌ Network connectivity between Docker containers
2. ❌ JSON format issue in user tracking API calls
3. ✅ User ID generation working
4. ✅ Tour generation working

## Debug Commands

**Check user in database:**
```bash
python -c "import requests; r=requests.get('http://192.168.0.217:5003/user/txzs7duahw03g810'); print('Found' if r.status_code==200 else 'Not found')"
```

**Test orchestrator directly:**
```bash
python -c "import requests; r=requests.post('http://192.168.0.217:5002/generate-complete-tour', json={'location':'Test','tour_type':'museum','total_stops':3,'user_id':'debug_test','request_string':'debug'}); print(r.status_code)"
```

The debug APK will show exactly where the user tracking is failing!