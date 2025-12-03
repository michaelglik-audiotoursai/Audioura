@echo off
echo ========================================
echo AudioTours Demo Environment Status Check
echo ========================================
echo.

echo 1. Checking Ubuntu VM connectivity...
ping -n 1 10.0.2.15 >nul 2>&1
if %errorlevel%==0 (
    echo ✅ Ubuntu VM is running and accessible
) else (
    echo ❌ Ubuntu VM is not running or not accessible
    echo    Please start VirtualBox and boot Ubuntu VM
)
echo.

echo 2. Checking VirtualBox port forwarding...
netstat -an | findstr ":8080" >nul 2>&1
if %errorlevel%==0 (
    echo ✅ Port 8080 is in use (possibly forwarded)
) else (
    echo ⚠️  Port 8080 not in use - may need to configure port forwarding
)
echo.

echo 3. Checking demo files...
if exist "start_flutter_web_demo.sh" (
    echo ✅ Web demo script exists
) else (
    echo ❌ Web demo script missing
)

if exist "test_flutter_web_demo.py" (
    echo ✅ Selenium test script exists
) else (
    echo ❌ Selenium test script missing
)

if exist "audioura-dev.apk" (
    echo ✅ Latest APK exists (audioura-dev.apk)
) else (
    echo ❌ APK file missing
)
echo.

echo 4. Checking current version...
if exist "audio_tour_app\pubspec.yaml" (
    findstr "version:" audio_tour_app\pubspec.yaml
) else (
    echo ❌ pubspec.yaml not found
)
echo.

echo ========================================
echo DEMO STARTUP INSTRUCTIONS:
echo ========================================
echo 1. Start VirtualBox and boot Ubuntu VM
echo 2. In Ubuntu terminal, run: bash start_flutter_web_demo.sh
echo 3. In Windows browser, go to: http://localhost:8080
echo 4. Run tests with: python test_flutter_web_demo.py
echo.

echo TROUBLESHOOTING:
echo - If VM won't start: Check VirtualBox settings
echo - If port forwarding fails: Verify NAT rule (TCP 8080->8080)
echo - If symlink errors: Use start_flutter_web_demo.sh (copies locally)
echo - If web storage fails: Check v1.2.8+103 shared_preferences
echo.
pause