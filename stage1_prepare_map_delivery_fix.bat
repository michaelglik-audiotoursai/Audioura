@echo off
echo ========================================
echo STAGE 1: Preparing Map Delivery Fix
echo ========================================

echo.
echo 1. Backing up current map_delivery/app.py...
copy "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py" "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py.backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%"

echo.
echo 2. The issue is that map_delivery/app.py is missing the download endpoints.
echo    However, map_delivery_service.py already has the correct implementation.

echo.
echo 3. Copying the complete service from map_delivery_service.py to map_delivery/app.py...
copy "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py" "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py"

echo.
echo 4. Creating comparison files for review...
echo    - Original: map_delivery\app.py.backup_*
echo    - New: map_delivery\app.py (copied from map_delivery_service.py)

echo.
echo ========================================
echo STAGE 1 COMPLETE - READY FOR REVIEW
echo ========================================
echo.
echo Please review the changes:
echo 1. Check map_delivery\app.py for the new endpoints:
echo    - /download-tour/^<int:tour_id^>
echo    - /tour-info/^<int:tour_id^>
echo.
echo 2. The new service includes proper logging and error handling
echo.
echo 3. When ready, run stage2_deploy_map_delivery_fix.bat
echo.
pause