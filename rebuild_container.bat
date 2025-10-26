@echo off
echo === Rebuilding the tour-orchestrator container ===

echo.
echo === Stopping the tour-orchestrator container ===
docker-compose stop tour-orchestrator

echo.
echo === Removing the tour-orchestrator container ===
docker-compose rm -f tour-orchestrator

echo.
echo === Creating a new Dockerfile for tour-orchestrator ===
echo FROM python:3.9-slim > Dockerfile.orchestrator.new
echo WORKDIR /app >> Dockerfile.orchestrator.new
echo COPY requirements_orchestrator.txt /app/requirements.txt >> Dockerfile.orchestrator.new
echo RUN pip install --no-cache-dir -r requirements.txt >> Dockerfile.orchestrator.new
echo COPY tour_orchestrator_service.py /app/ >> Dockerfile.orchestrator.new
echo EXPOSE 5002 >> Dockerfile.orchestrator.new
echo CMD ["python", "tour_orchestrator_service.py"] >> Dockerfile.orchestrator.new

echo.
echo === Creating requirements file ===
echo flask==1.1.4 > requirements_orchestrator.txt
echo flask-cors==3.0.10 >> requirements_orchestrator.txt
echo requests==2.28.1 >> requirements_orchestrator.txt
echo psycopg2-binary==2.9.1 >> requirements_orchestrator.txt
echo werkzeug==1.0.1 >> requirements_orchestrator.txt
echo markupsafe==1.1.1 >> requirements_orchestrator.txt
echo itsdangerous==1.1.0 >> requirements_orchestrator.txt
echo jinja2==2.11.3 >> requirements_orchestrator.txt

echo.
echo === Fixing the orchestrate_tour_async function ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\direct_fix.py c:\temp\fixed_function.py

echo.
echo === Creating a complete fixed file ===
type c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py > c:\temp\tour_orchestrator_fixed.py

echo.
echo === Updating coordinates service URL in the file ===
powershell -Command "(Get-Content c:\temp\tour_orchestrator_fixed.py) -replace 'http://coordinates-fromai:5004/coordinates/', 'http://coordinates-fromai:5006/coordinates/' | Set-Content c:\temp\tour_orchestrator_fixed.py"

echo.
echo === Updating timeout in the file ===
powershell -Command "(Get-Content c:\temp\tour_orchestrator_fixed.py) -replace 'timeout=30', 'timeout=60' | Set-Content c:\temp\tour_orchestrator_fixed.py"

echo.
echo === Copying the fixed file back to the development directory ===
copy c:\temp\tour_orchestrator_fixed.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py

echo.
echo === Rebuilding the tour-orchestrator container ===
docker-compose build tour-orchestrator

echo.
echo === Starting the tour-orchestrator container ===
docker-compose up -d tour-orchestrator

echo.
echo === Done! ===
echo The tour-orchestrator container has been rebuilt with the fixed function.
pause