@echo off
echo ===========================================
echo Cleaning Up Newsletter Services
echo ===========================================

echo.
echo Stopping and removing newsletter containers...
docker stop newsletter-link-extractor-1 2>nul
docker rm newsletter-link-extractor-1 2>nul

docker stop background-article-processor-1 2>nul
docker rm background-article-processor-1 2>nul

docker stop simple-news-search-1 2>nul
docker rm simple-news-search-1 2>nul

echo.
echo Removing newsletter images...
docker rmi newsletter-link-extractor:1.2.2.82 2>nul
docker rmi background-article-processor:1.2.2.82 2>nul
docker rmi simple-news-search:1.2.2.82 2>nul

echo.
echo Checking port availability...
netstat -an | findstr :5011
netstat -an | findstr :5012
netstat -an | findstr :5013

echo.
echo Newsletter services cleanup complete!
echo Ports 5011, 5012, 5013 should now be available.
echo.
pause