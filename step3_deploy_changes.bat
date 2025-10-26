@echo off
echo === Step 3: Deploy changes to containers ===

echo.
echo === Copying modified_generate_tour_text.py to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\modified_generate_tour_text.py development-tour-generator-1:/app/

echo.
echo === Copying generate_tour_text_service.py to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py development-tour-generator-1:/app/

echo.
echo === Restarting tour-generator container ===
docker-compose restart tour-generator

echo.
echo === Done with Step 3 ===
echo The changes have been deployed to the container and the service has been restarted.
pause