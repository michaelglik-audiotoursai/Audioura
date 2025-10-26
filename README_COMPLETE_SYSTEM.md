# Complete Audio Tour Generation System

A complete Docker-based system with three services that work together to generate audio tours.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Tour Generator  │    │ Tour Processor  │    │ Tour           │
│ (Port 5000)     │    │ (Port 5001)     │    │ Orchestrator   │
│                 │    │                 │    │ (Port 5002)    │
│ • OpenAI API    │    │ • Text → Audio  │    │ • Complete     │
│ • Text          │    │ • Single HTML   │    │   Pipeline     │
│   Generation    │    │ • Netlify Ready │    │ • One-Click    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Services

### 1. Tour Generator (Port 5000)
- Generates tour text using OpenAI API
- Creates detailed descriptions for each stop
- Handles POI information and directions

### 2. Tour Processor (Port 5001)  
- Converts text to audio files (MP3)
- Creates single HTML file with embedded audio
- Prepares Netlify-ready deployment packages

### 3. Tour Orchestrator (Port 5002) - **NEW!**
- **One-click complete tour generation**
- Orchestrates the entire pipeline automatically
- Manages the 7-step process from start to finish
- Returns ready-to-deploy packages

## Quick Start

### Deploy All Services
```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-openai-api-key"

# Start all three services
docker-compose -f docker-compose-complete.yml up -d

# Check all services are running
curl http://localhost:5000/health  # Tour Generator
curl http://localhost:5001/health  # Tour Processor  
curl http://localhost:5002/health  # Tour Orchestrator
```

## Usage

### Option 1: Complete Pipeline (Recommended)
**One API call does everything:**

```bash
# Generate complete tour
curl -X POST http://localhost:5002/generate-complete-tour \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Fruitlands Museum, Harvard, Massachusetts",
    "tour_type": "exhibit", 
    "total_stops": 25
  }'

# Returns: {"job_id": "abc123...", "status": "queued"}

# Check progress
curl http://localhost:5002/status/abc123...

# Download when complete
curl -O http://localhost:5002/download/abc123...
```

### Option 2: Individual Services
Use services separately for custom workflows:

```bash
# 1. Generate text
curl -X POST http://localhost:5000/generate ...

# 2. Process to audio/HTML  
curl -X POST http://localhost:5001/process ...

# 3. Download results
curl -O http://localhost:5001/download/...
```

## API Endpoints

### Tour Orchestrator (Port 5002)
- `POST /generate-complete-tour` - One-click complete generation
- `GET /status/{job_id}` - Check progress
- `GET /download/{job_id}` - Download Netlify package
- `GET /serve/{job_id}` - Get serving instructions
- `GET /jobs` - List all jobs
- `GET /health` - Health check

### Individual Services
- **Tour Generator (5000)**: `/generate`, `/status/{id}`, `/download/{id}`
- **Tour Processor (5001)**: `/process`, `/status/{id}`, `/download/{id}`

## Complete Workflow

The orchestrator handles this entire process automatically:

1. ✅ **Generate tour text** (OpenAI API)
2. ✅ **Download text file**
3. ✅ **Upload to processor**  
4. ✅ **Convert text → audio**
5. ✅ **Create single HTML file**
6. ✅ **Package for Netlify**
7. ✅ **Return deployment-ready ZIP**

## Output

You get a ZIP file containing:
- `index.html` - Complete tour with embedded audio
- `manifest.json` - PWA manifest
- `service-worker.js` - Offline functionality

**Ready for immediate Netlify deployment!**

## Management

```bash
# View all running jobs
curl http://localhost:5002/jobs

# Stop all services
docker-compose -f docker-compose-complete.yml down

# View logs
docker-compose -f docker-compose-complete.yml logs -f

# Restart services
docker-compose -f docker-compose-complete.yml restart
```

## Benefits

✅ **One-click generation** - Single API call does everything  
✅ **Automatic orchestration** - No manual steps required  
✅ **Progress tracking** - Real-time status updates  
✅ **Error handling** - Comprehensive error reporting  
✅ **Scalable** - Each service can be scaled independently  
✅ **Netlify ready** - Immediate deployment capability  

## Ports

- **5000**: Tour Generator (OpenAI text generation)
- **5001**: Tour Processor (Audio + HTML creation)  
- **5002**: Tour Orchestrator (Complete pipeline)

The orchestrator service makes the entire system as simple as one API call!