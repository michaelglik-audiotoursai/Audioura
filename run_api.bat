@echo off
echo Installing required packages...
pip install flask psycopg2-binary

echo.
echo Starting API server on port 5003...
python fix_api.py