@echo off
echo ===========================================
echo Deploying Newsletter Services v1.2.2.82
echo Following AudioTours Development Workflow
echo ===========================================

echo.
echo Step 1: Building Newsletter Link Extractor Service...
docker build -f Dockerfile.newsletter-link-extractor -t newsletter-link-extractor:1.2.2.82 .
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to build newsletter-link-extractor
    pause
    exit /b 1
)

echo.
echo Step 2: Building Background Article Processor Service...
docker build -f Dockerfile.background-article-processor -t background-article-processor:1.2.2.82 .
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to build background-article-processor
    pause
    exit /b 1
)

echo.
echo Step 3: Building Simple News Search Service...
docker build -f Dockerfile.simple-news-search -t simple-news-search:1.2.2.82 .
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to build simple-news-search
    pause
    exit /b 1
)

echo.
echo Step 4: Starting Newsletter Link Extractor (Port 5014)...
docker run -d --name newsletter-link-extractor-1 --network development_default -p 5014:5000 --restart unless-stopped newsletter-link-extractor:1.2.2.82
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start newsletter-link-extractor-1
    pause
    exit /b 1
)

echo.
echo Step 5: Starting Background Article Processor (Port 5015)...
docker run -d --name background-article-processor-1 --network development_default -p 5015:5000 --restart unless-stopped background-article-processor:1.2.2.82
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start background-article-processor-1
    pause
    exit /b 1
)

echo.
echo Step 6: Starting Simple News Search (Port 5016)...
docker run -d --name simple-news-search-1 --network development_default -p 5016:5000 --restart unless-stopped simple-news-search:1.2.2.82
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start simple-news-search-1
    pause
    exit /b 1
)

echo.
echo Step 7: Verifying Service Status...
echo.
echo Newsletter Services Status:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr newsletter
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr background-article
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr simple-news

echo.
echo Step 8: Testing Service Health...
echo Testing Newsletter Link Extractor...
curl -s http://localhost:5014 > nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Newsletter Link Extractor: HEALTHY
) else (
    echo ✗ Newsletter Link Extractor: NOT RESPONDING
)

echo Testing Background Article Processor...
curl -s http://localhost:5015 > nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Background Article Processor: HEALTHY
) else (
    echo ✗ Background Article Processor: NOT RESPONDING
)

echo Testing Simple News Search...
curl -s http://localhost:5016 > nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Simple News Search: HEALTHY
) else (
    echo ✗ Simple News Search: NOT RESPONDING
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
echo Next Steps:
echo 1. Test Flutter app with Article/Newsletter switch
echo 2. Update Home page to show processed articles
echo 3. Commit changes with version tag v1.2.2.82
echo.
echo Deployment complete! Services are ready for testing.