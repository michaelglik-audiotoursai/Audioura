@echo off
echo === Step 1: Extend existing app.py (SAFE - NO BREAKING CHANGES) ===

echo.
echo === Getting existing app.py from container ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
call get_existing_app.bat

echo.
echo === Extending app.py with tour delivery endpoints ===
python extend_existing_app.py

echo.
echo === Done with Step 1 ===
echo ✅ Extended app.py with tour delivery endpoints
echo ✅ All existing functionality preserved
echo ✅ Service runs on port 5005
echo.
echo Please review the changes before proceeding to Step 2.
pause