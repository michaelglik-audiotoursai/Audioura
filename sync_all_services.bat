@echo off
echo === Synchronizing all service files between development directory and containers ===

echo.
echo === Copying FROM containers TO development directory ===
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py tour_orchestrator_service.py
docker cp development-tour-generator-1:/app/generate_tour_text_service.py generate_tour_text_service.py
docker cp development-tour-generator-1:/app/modified_generate_tour_text.py modified_generate_tour_text.py
docker cp development-tour-processor-1:/app/tour_processor_service.py tour_processor_service.py
docker cp development-map-delivery-1:/app/app.py map_delivery_service.py
docker cp development-coordinates-fromai-1:/app/app.py coordinates_fromai_service.py

echo.
echo === Copying FROM development directory TO containers ===
docker cp tour_orchestrator_service.py development-tour-orchestrator-1:/app/
docker cp generate_tour_text_service.py development-tour-generator-1:/app/
docker cp modified_generate_tour_text.py development-tour-generator-1:/app/
docker cp tour_processor_service.py development-tour-processor-1:/app/
docker cp map_delivery_service.py development-map-delivery-1:/app/app.py
docker cp coordinates_fromai_service.py development-coordinates-fromai-1:/app/app.py

echo.
echo === Restarting all services ===
docker-compose restart

echo.
echo === Done! ===
echo All service files are now synchronized between development directory and containers.
pause