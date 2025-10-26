@echo off
echo ===========================================
echo Starting All AudioTours Services v1.2.2.82
echo With Auto-Restart Configuration
echo ===========================================

echo.
echo Option 1: Start using Master Docker Compose (RECOMMENDED)
echo This will start ALL services with auto-restart enabled
echo.
set /p choice1="Use master compose file? (y/n): "
if /i "%choice1%"=="y" (
    echo Starting all services with master compose...
    docker-compose -f docker-compose-master.yml up -d
    goto :check_status
)

echo.
echo Option 2: Start services individually
echo.
echo Starting Core Services...
docker-compose up -d

echo.
echo Starting News Services...
docker-compose -f docker-compose-news.yml up -d

echo.
echo Starting Newsletter Services...
docker-compose -f docker-compose-newsletter.yml up -d

:check_status
echo.
echo ===========================================
echo Checking Service Status...
echo ===========================================

timeout /t 5 /nobreak > nul

echo.
echo Core Services:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr -E "(tour-|postgres-|user-|coordinates-|map-|treats|voice-)"

echo.
echo News Services:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr news-

echo.
echo Newsletter Services:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr -E "(newsletter-|background-|simple-news)"

echo.
echo ===========================================
echo Auto-Restart Status Check
echo ===========================================
echo.
echo Services with auto-restart enabled:
docker ps --format "table {{.Names}}\t{{.Status}}" | findstr "unless-stopped"

echo.
echo ===========================================
echo All Services Started!
echo ===========================================
echo.
echo Key Ports:
echo - Tour Generator: 5000
echo - Tour Orchestrator: 5002  
echo - News Orchestrator: 5012
echo - Newsletter Link Extractor: 5014
echo - Background Article Processor: 5015
echo - Simple News Search: 5016
echo.
echo All services will now auto-start when Docker starts!
echo.
pause