@echo off
echo Restarting tour orchestrator service...
docker restart development-tour-orchestrator-1
echo Done! Tour orchestrator service has been restarted.
echo.
echo You can check the logs with: docker logs development-tour-orchestrator-1