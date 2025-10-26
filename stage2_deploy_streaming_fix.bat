@echo off
echo ========================================
echo STAGE 2: Deploying Streaming Download Fix
echo ========================================

echo.
echo 1. Copying optimized service to Docker container...
docker cp "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py" development-map-delivery-1:/app/app.py

echo.
echo 2. Restarting map-delivery container...
docker restart development-map-delivery-1

echo.
echo 3. Waiting for service to restart...
timeout /t 8

echo.
echo 4. Testing the optimized download endpoint...
echo Testing health:
curl -f http://192.168.0.217:5005/health

echo.
echo Testing download headers (should show Content-Length):
curl -I http://192.168.0.217:5005/download-tour/6

echo.
echo 5. Committing changes to Git...
git add map_delivery/app.py
git commit -m "Optimize download streaming - use chunked response for large files (backend fix)"
git push origin master

echo.
echo ========================================
echo DEPLOYMENT COMPLETE
echo ========================================
echo.
echo Backend optimizations applied:
echo - Streaming download with 8KB chunks
echo - Proper Content-Length headers
echo - Memory-efficient large file handling
echo.
echo Mobile app timeout increased to 120s (v169 building)
echo Combined fix should resolve download issues on slower connections.