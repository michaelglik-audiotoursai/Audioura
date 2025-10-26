@echo off
echo Cleaning up newsletters with no articles...

curl -X POST http://192.168.0.217:5017/cleanup_empty_newsletters ^
  -H "Content-Type: application/json"

echo.
echo Cleanup completed!