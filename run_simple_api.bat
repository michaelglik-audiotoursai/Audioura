@echo off
echo Installing required packages...
pip install flask psycopg2-binary

echo.
echo Starting simple API server on port 5003...
python simple_api_server.py