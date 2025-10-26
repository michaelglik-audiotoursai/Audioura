@echo off
echo Deploying Newsletter Services v1.2.2.82

echo Building newsletter services...
docker build -f Dockerfile.newsletter-link-extractor -t newsletter-link-extractor:1.2.2.82 .
docker build -f Dockerfile.background-article-processor -t background-article-processor:1.2.2.82 .
docker build -f Dockerfile.simple-news-search -t simple-news-search:1.2.2.82 .

echo Starting newsletter services...
docker run -d --name newsletter-link-extractor-1 --network development_default -p 5011:5000 newsletter-link-extractor:1.2.2.82
docker run -d --name background-article-processor-1 --network development_default -p 5012:5000 background-article-processor:1.2.2.82
docker run -d --name simple-news-search-1 --network development_default -p 5013:5000 simple-news-search:1.2.2.82

echo Checking service status...
docker ps | findstr newsletter
docker ps | findstr background-article
docker ps | findstr simple-news

echo Newsletter services deployed successfully!
echo Link Extractor: http://localhost:5011
echo Article Processor: http://localhost:5012  
echo News Search: http://localhost:5013