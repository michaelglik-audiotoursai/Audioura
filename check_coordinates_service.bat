@echo off
echo === Checking coordinates service status ===

echo.
echo === Checking if coordinates-fromai container is running ===
docker ps | findstr coordinates-fromai

echo.
echo === Checking coordinates service logs ===
docker logs development-coordinates-fromai-1

echo.
echo === Done! ===
pause