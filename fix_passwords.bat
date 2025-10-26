@echo off
echo Fixing database passwords in newsletter services...

powershell -Command "(Get-Content simple_news_search_service.py) -replace 'password=\"\"password\"\"', 'password=\"\"password123\"\"' | Set-Content simple_news_search_service.py"

echo Database passwords updated!