@echo off
echo ===========================================
echo Committing Newsletter Feature v1.2.2.82
echo Following AudioTours Version Management
echo ===========================================

echo.
echo Step 1: Adding all modified files...
git add newsletter_link_extractor_service.py
git add background_article_processor_service.py
git add simple_news_search_service.py
git add Dockerfile.newsletter-link-extractor
git add Dockerfile.background-article-processor
git add Dockerfile.simple-news-search
git add docker-compose-newsletter.yml
git add requirements-newsletter.txt
git add audio_tour_app/pubspec.yaml
git add audio_tour_app/lib/screens/tour_generator_screen.dart
git add deploy_newsletter_services.bat
git add deploy_newsletter_services_step_by_step.bat

echo.
echo Step 2: Committing with version tag...
git commit -m "v1.2.2.82 - Add Newsletter Processing Feature - Article/Newsletter switch, link extraction, background processing"

echo.
echo Step 3: Creating version tag...
git tag "v1.2.2.82"

echo.
echo Step 4: Pushing to master with tags...
git push origin master --tags

echo.
echo ===========================================
echo Newsletter Feature v1.2.2.82 Committed!
echo ===========================================
echo.
echo Changes committed:
echo - Newsletter link extraction service
echo - Background article processing service  
echo - Simple database search service
echo - Article/Newsletter switch in Generate page
echo - Version synchronization across all services
echo.
echo GitHub Actions will now build APK v1.2.2.82
echo.
pause