@echo off
echo === Checking Docker network connectivity ===

echo.
echo === Listing Docker networks ===
docker network ls

echo.
echo === Inspecting development network ===
docker network inspect development_default

echo.
echo === Checking container connectivity ===
docker exec -it development-tour-orchestrator-1 ping -c 3 tour-generator
docker exec -it development-tour-orchestrator-1 ping -c 3 tour-processor
docker exec -it development-tour-orchestrator-1 ping -c 3 coordinates-fromai

echo.
echo === Done! ===
pause