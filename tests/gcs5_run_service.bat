@echo off
REM Launch the tour-editing service in cloud-equivalent mode for GCS-5 verification.
REM Usage: gcs5_run_service.bat <service_file.py> <port>
set DB_HOST=127.0.0.1
set DB_PORT=5544
set DB_NAME=audiotours
set DB_USER=admin
set DB_PASSWORD=password123
set TOUR_STORAGE_MODE=cloud
set BLOB_STORAGE_TYPE=r2
set R2_ENDPOINT=http://127.0.0.1:9010
set R2_BUCKET=v1-audiotours-r2-bucket
set R2_ACCESS_KEY_ID=minioadmin
set R2_SECRET_ACCESS_KEY=minioadmin
set POLLY_TTS_URL=http://127.0.0.1:5599
set AWS_ACCESS_KEY_ID=dummy
set AWS_SECRET_ACCESS_KEY=dummy
set AWS_DEFAULT_REGION=us-east-1
set PORT=%2
python "%1"
