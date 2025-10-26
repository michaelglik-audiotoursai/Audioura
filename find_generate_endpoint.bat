@echo off
echo === Finding /generate endpoint in tour-generator service ===

echo === Creating backup of generate_tour_text_service.py ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py.bak1

echo.
echo === Copying the main Python file from the container ===
docker cp development-tour-generator-1:/app/generate_tour_text_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py

echo.
echo === Searching for /generate endpoint ===
findstr /C:"@app.route('/generate'" c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py

echo.
echo === Done! ===
echo The generate_tour_text_service.py file has been copied to your development directory and its backup: c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py.bak1.
echo You can examine it to see what function is mapped to the /generate endpoint.
pause