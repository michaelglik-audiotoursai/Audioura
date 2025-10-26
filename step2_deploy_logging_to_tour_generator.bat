@echo off
echo === Step 2: Deploy logging to tour-generator container ===

echo.
echo === Copying updated file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py development-tour-generator-1:/app/

echo.
echo === Restarting tour-generator container ===
docker-compose restart tour-generator

echo.
echo === Done with Step 2 ===
echo The updated file has been deployed to the container and the service has been restarted.
pause