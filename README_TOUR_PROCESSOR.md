# Tour Processing Service

A REST API service that processes tour text files into deployable Netlify directories through a complete pipeline.

## Pipeline Steps

1. **text_to_index.py** - Converts text to audio files and creates web page
2. **single_file_app_builder.py** - Creates single HTML file with embedded audio
3. **prepare_for_netlify.py** - Prepares directory for Netlify deployment

## API Endpoints

### Health Check
```
GET /health
```

### Upload Tour File
```
POST /upload
Content-Type: multipart/form-data

Form field: file (tour text file)
```

### Process Tour
```
POST /process
Content-Type: application/json

{
  "tour_file": "openaiapi_generated_tour_path_2_for_decordova_sculpture_park.txt"
}
```

### Check Status
```
GET /status/{job_id}
```

### Download Result
```
GET /download/{job_id}
```
Downloads a ZIP file ready for Netlify deployment.

### List Files
```
GET /files
```
Lists all uploaded tour text files.

### List Jobs
```
GET /jobs
```
Lists all processing jobs.

## Deployment

### Start Service
```bash
docker-compose -f docker-compose-tour-processor.yml up -d
```

### Check Status
```bash
curl http://localhost:5001/health
```

## Usage Example

### 1. Upload Tour File
```bash
curl -X POST -F "file=@your_tour.txt" http://localhost:5001/upload
```

### 2. Process Tour
```bash
curl -X POST http://localhost:5001/process \
  -H "Content-Type: application/json" \
  -d '{"tour_file": "your_tour.txt"}'
```

### 3. Check Progress
```bash
curl http://localhost:5001/status/your-job-id
```

### 4. Download Netlify Package
```bash
curl -O http://localhost:5001/download/your-job-id
```

### 5. Deploy to Netlify
1. Extract the downloaded ZIP file
2. Drag the extracted folder to Netlify's deploy area
3. Your tour is live!

## Output

The service produces a ZIP file containing a complete Netlify-ready directory:
- `index.html` - Single-file tour app with embedded audio (renamed from the single HTML file)
- `manifest.json` - PWA manifest for mobile app functionality
- `service-worker.js` - Offline functionality and caching

This directory structure is ready for immediate deployment to Netlify by:
1. Extracting the ZIP file
2. Dragging the extracted folder to Netlify's deploy area
3. Your tour goes live instantly!

## Dependencies

- Python 3.9
- Flask for REST API
- espeak for text-to-speech
- ffmpeg for audio processing
- All existing tour processing scripts

## Port

Service runs on port **5001** (different from the tour generation service on 5000).