@echo off
setlocal enabledelayedexpansion

if "%1"=="" (
    echo Usage: version_management.bat [commit^|deploy^|rollback] [version]
    echo.
    echo Commands:
    echo   commit 1.1.0.2    - Commit current changes as version 1.1.0.2
    echo   deploy 1.1.0.2    - Deploy version 1.1.0.2 to services and trigger APK build
    echo   rollback 1.1.0.1  - Rollback to version 1.1.0.1 (services + mobile)
    echo.
    echo Current mobile version:
    findstr "version:" audio_tour_app\pubspec.yaml
    echo.
    echo Current service versions:
    findstr "SERVICE_VERSION" *.py
    exit /b 1
)

set COMMAND=%1
set VERSION=%2

if "%VERSION%"=="" (
    echo Error: Version number required
    exit /b 1
)

echo ========================================
echo AudioTours Version Management
echo Command: %COMMAND%
echo Version: %VERSION%
echo ========================================

if "%COMMAND%"=="commit" goto :commit
if "%COMMAND%"=="deploy" goto :deploy  
if "%COMMAND%"=="rollback" goto :rollback
echo Error: Unknown command %COMMAND%
exit /b 1

:commit
echo.
echo STEP 1: Updating mobile app version to %VERSION%
powershell -Command "(Get-Content audio_tour_app\pubspec.yaml) -replace 'version: .*', 'version: %VERSION%' | Set-Content audio_tour_app\pubspec.yaml"

echo.
echo STEP 2: Updating service versions to %VERSION%
for %%f in (*.py) do (
    findstr /l "SERVICE_VERSION" "%%f" >nul
    if !errorlevel! equ 0 (
        echo Updating %%f
        powershell -Command "(Get-Content '%%f') -replace 'SERVICE_VERSION = \".*\"', 'SERVICE_VERSION = \"%VERSION%\"' | Set-Content '%%f'"
    )
)

echo.
echo STEP 3: Adding all changes to Git
git add .

echo.
echo STEP 4: Committing with version tag
git commit -m "v%VERSION% - Voice control audio initialization fix"

echo.
echo STEP 5: Creating Git tag
git tag "v%VERSION%"

echo.
echo STEP 6: Pushing to GitHub (triggers APK build)
git push origin master --tags

echo.
echo ✅ Version %VERSION% committed and pushed!
echo ✅ GitHub Actions will build APK automatically
echo ✅ Check GitHub releases for APK in ~5-10 minutes
goto :end

:deploy
echo.
echo STEP 1: Checking out version %VERSION%
git checkout "v%VERSION%"

echo.
echo STEP 2: Copying files to tour-processor container only
docker cp single_file_app_builder.py development-tour-processor-1:/app/single_file_app_builder.py
docker cp tour_generation_service.py development-tour-processor-1:/app/tour_generation_service.py

echo.
echo STEP 3: Restarting tour-processor service
docker restart development-tour-processor-1

echo.
echo STEP 4: Checking service health
timeout /t 5
echo Tour Processor Health:
docker exec development-tour-processor-1 curl -s http://localhost:5001/health 2>nul

echo.
echo ✅ Services deployed to version %VERSION%!
echo ✅ Download APK v%VERSION% from GitHub releases
goto :end

:rollback
echo.
echo STEP 1: Checking out version %VERSION%
git checkout "v%VERSION%"

echo.
echo STEP 2: Copying files to tour-processor container only
docker cp single_file_app_builder.py development-tour-processor-1:/app/single_file_app_builder.py
docker cp tour_generation_service.py development-tour-processor-1:/app/tour_generation_service.py

echo.
echo STEP 3: Restarting tour-processor service
docker restart development-tour-processor-1

echo.
echo STEP 4: Checking service health
timeout /t 5
echo Tour Processor Health:
docker exec development-tour-processor-1 curl -s http://localhost:5001/health 2>nul

echo.
echo ✅ Rolled back to version %VERSION%!
echo ✅ Download APK v%VERSION% from GitHub releases
echo.
echo To return to latest: git checkout master
goto :end

:end
echo.
echo ========================================
echo Version Management Complete
echo ========================================