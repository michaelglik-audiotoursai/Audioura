@echo off
echo === Checking synchronization status between development directory and containers ===

echo.
echo === Comparing file timestamps ===

echo Tour Orchestrator:
dir /tc tour_orchestrator_service.py 2>nul | find "tour_orchestrator_service.py"
docker exec development-tour-orchestrator-1 ls -la /app/tour_orchestrator_service.py

echo.
echo Tour Generator:
dir /tc modified_generate_tour_text.py 2>nul | find "modified_generate_tour_text.py"
docker exec development-tour-generator-1 ls -la /app/modified_generate_tour_text.py

echo.
echo Map Delivery:
dir /tc map_delivery_service.py 2>nul | find "map_delivery_service.py"
docker exec development-map-delivery-1 ls -la /app/app.py

echo.
echo === File size comparison ===
echo Local modified_generate_tour_text.py:
for %%f in (modified_generate_tour_text.py) do echo %%~zf bytes

echo Container modified_generate_tour_text.py:
docker exec development-tour-generator-1 wc -c /app/modified_generate_tour_text.py

echo.
echo === Done! ===
pause