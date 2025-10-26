@echo off
echo Testing news download endpoints...
echo.

echo 1. Testing health check:
curl -s http://192.168.0.217:5012/health
echo.
echo.

echo 2. Testing download with article ID cac20923-3452-4d8a-8b3d-cc7e0977e7f5:
curl -I http://192.168.0.217:5012/download/cac20923-3452-4d8a-8b3d-cc7e0977e7f5
echo.
echo.

echo 3. Testing old URL (should fail):
curl -I http://192.168.0.217:5012/download-news/cac20923-3452-4d8a-8b3d-cc7e0977e7f5
echo.
echo.

echo 4. Checking if news-orchestrator container is running:
docker ps | findstr news-orchestrator
echo.

echo Test completed!