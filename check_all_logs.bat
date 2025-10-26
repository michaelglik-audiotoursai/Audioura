@echo off
echo === Checking logs for all services ===

echo.
echo === tour-orchestrator logs ===
docker logs development-tour-orchestrator-1 --tail 50

echo.
echo === tour-generator logs ===
docker logs development-tour-generator-1 --tail 50

echo.
echo === coordinates-fromai logs ===
docker logs development-coordinates-fromai-1 --tail 50

echo.
echo === tour-processor logs ===
docker logs development-tour-processor-1 --tail 50

echo.
echo === user-api-2 logs ===
docker logs development-user-api-2-1 --tail 50

echo.
echo === tour-update logs ===
docker logs development-tour-update-1 --tail 50

echo.
echo === map-delivery logs ===
docker logs development-map-delivery-1 --tail 50

echo.
echo === Done! ===
pause