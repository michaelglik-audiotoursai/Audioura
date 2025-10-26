@echo off
echo 🔧 Testing Debug APK Setup
echo =========================

echo 📱 Debug APK Location: build\app\outputs\flutter-apk\app-debug.apk
echo 🔍 Testing user tracking service...

python -c "import requests; r=requests.get('http://192.168.0.217:5003/users'); print(f'Users: {r.json().get(\"total_users\", 0)}' if r.status_code==200 else f'Error: {r.status_code}')"

echo.
echo ✅ Debug APK ready with full logging enabled
echo 📋 Next steps:
echo 1. Install: adb install build\app\outputs\flutter-apk\app-debug.apk
echo 2. Monitor logs: adb logcat -s flutter
echo 3. Generate tour from app to test tracking
echo.
pause