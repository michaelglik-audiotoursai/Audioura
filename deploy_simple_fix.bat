@echo off
echo === Deploying simple coordinates fix to container ===

echo.
echo === Copying updated file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done with Step 2 ===
echo The updated file has been deployed to the container and the service has been restarted.
pause