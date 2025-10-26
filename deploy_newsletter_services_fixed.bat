@echo off
echo ===========================================
echo Deploying Newsletter Services v1.2.2.82
echo Using Docker Compose (Like News Services)
echo ===========================================

echo.
echo Step 1: Stopping existing newsletter services...
docker-compose -f docker-compose-newsletter.yml down

echo.
echo Step 2: Building and starting newsletter services...
docker-compose -f docker-compose-newsletter.yml up -d --build

echo.
echo Step 3: Waiting for services to start...
timeout /t 10 /nobreak > nul

echo.
echo Step 4: Checking service status...
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr -E "(newsletter-|background-|simple-news)"

echo.
echo Step 5: Testing service health...
echo Testing Newsletter Link Extractor (Port 5014)...
curl -s http://localhost:5014 > nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Newsletter Link Extractor: HEALTHY
) else (
    echo ✗ Newsletter Link Extractor: NOT RESPONDING
)

echo Testing Background Article Processor (Port 5015)...
curl -s http://localhost:5015 > nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Background Article Processor: HEALTHY
) else (
    echo ✗ Background Article Processor: NOT RESPONDING
)

echo Testing Simple News Search (Port 5016)...
curl -s http://localhost:5016 > nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Simple News Search: HEALTHY
) else (
    echo ✗ Simple News Search: NOT RESPONDING
)

echo.
echo Step 6: Checking network connectivity...
docker exec newsletter-link-extractor-1 ping -c 1 news-orchestrator-1 > nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo ✓ Newsletter services can reach news-orchestrator-1
) else (
    echo ✗ Network connectivity issue detected
)

echo.
echo ===========================================
echo Newsletter Services Deployment Complete!
echo ===========================================
echo.
echo Service Endpoints:
echo - Newsletter Link Extractor: http://localhost:5014
echo - Background Article Processor: http://localhost:5015  
echo - Simple News Search: http://localhost:5016
echo.
echo All services are now on development_default network
echo with unique internal ports (5014, 5015, 5016)
echo.
echo Deployment complete! Services are ready for testing.