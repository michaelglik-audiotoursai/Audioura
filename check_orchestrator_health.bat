@echo off
echo Checking tour orchestrator health...

echo Testing HTTP endpoint...
curl -s http://localhost:5002/health

echo.
echo Checking container status...
docker ps | findstr tour-orchestrator

echo.
echo Checking container network...
docker inspect development-tour-orchestrator-1 -f "Network: {{range $net, $conf := .NetworkSettings.Networks}}{{$net}}{{end}}"

echo.
echo Done!