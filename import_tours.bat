@echo off
echo Importing tours to database...

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python is not installed or not in PATH. Please install Python.
    exit /b 1
)

REM Check if required packages are installed
echo Checking required packages...
pip install psycopg2-binary openai requests

REM Run the import script
echo Running import script...
python import_tours_to_db.py %*

echo Done!
pause