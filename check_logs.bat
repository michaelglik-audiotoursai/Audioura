@echo off
echo === Checking tour-orchestrator logs ===

echo.
echo === Getting the last 100 lines of logs ===
docker logs --tail 100 development-tour-orchestrator-1

echo.
echo === Done! ===
pause