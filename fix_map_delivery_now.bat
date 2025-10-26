@echo off
echo Backing up current map_delivery/app.py...
copy "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py" "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py.backup"

echo Copying complete service from map_delivery_service.py to map_delivery/app.py...
copy "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py" "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py"

echo Copying to Docker container...
docker cp "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py" development-map-delivery-1:/app/app.py

echo Restarting map-delivery container...
docker restart development-map-delivery-1

echo Waiting for service to start...
timeout /t 5

echo Testing endpoints...
curl -f http://192.168.0.217:5005/health

echo Fix complete!