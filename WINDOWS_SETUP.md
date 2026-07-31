# Windows Setup Guide — AudioTours `storied` Branch

## Prerequisites

- **Docker Desktop for Windows** (with WSL2 backend recommended)
- **Git for Windows**
- **`.env` file** (transferred via USB — never committed to the repo)

## Clone & Checkout

```powershell
git clone https://github.com/michaelglik-audiotoursai/Audioura.git
cd Audioura
git checkout storied
```

## Manual Setup

### 1. Place the `.env` file

Copy `.env` from the USB drive into the repo root (`Audioura/.env`).

Required keys:
```
OPENAI_API_KEY=sk-...
SERP_API_KEY=...
SERP_PROVIDER=serper
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

### 2. Create the Docker network

```powershell
docker network create development_default
```

### 3. Disable AirPlay / port 5000 conflict (if applicable)

On macOS, AirPlay Receiver uses port 5000. On Windows this is typically not
an issue, but if anything occupies port 5000:

```powershell
netstat -ano | findstr :5000
```

Kill the process or change the host port mapping in `docker-compose-master.yml`.

### 4. Architecture note (amd64 vs arm64)

The Mac Mini builds arm64 images. Windows (Intel/AMD) builds amd64 natively.
All Dockerfiles use standard `python:3.9-slim` or `python:3.11-slim` base
images that support both architectures — no platform flags needed.

Do **not** copy images from the Mac Mini. Always build fresh on Windows.

## Build & Start

```powershell
docker compose -f docker-compose-master.yml up -d --build
```

First build takes 5–10 minutes (downloading base images + pip installs).

## Health Checks

Once running, verify:

```powershell
# Postgres (host port 5433, NOT 5432)
docker exec development-postgres-2-1 pg_isready -U admin -d audiotours

# Tour Generator
curl http://localhost:5000/health

# Tour Orchestrator
curl http://localhost:5002/health

# Tour Processor
curl http://localhost:5001/health

# Coordinates service
curl http://localhost:5006/health

# Map Delivery
curl http://localhost:5005/health

# Voice Control
curl http://localhost:5008/health
```

All should return 200 OK or equivalent healthy response.

## End-to-End Tour Generation Test

Generate a test tour to confirm the full pipeline works:

```powershell
curl -X POST http://localhost:5002/generate-tour ^
  -H "Content-Type: application/json" ^
  -d "{\"venue_name\": \"Boston Public Library\", \"venue_type\": \"library\", \"language\": \"en\"}"
```

**Expected output** (abbreviated):
```json
{
  "status": "success",
  "tour_id": "...",
  "message": "Tour generation started"
}
```

A successful response means the orchestrator accepted the request and
dispatched it to the generator. Check logs for completion:

```powershell
docker compose -f docker-compose-master.yml logs -f tour-generator --tail=50
```

Look for: `"Tour generation complete"` or a file written to `tours/`.

## Postgres Connection (for debugging)

```
Host: localhost
Port: 5433  (NOT 5432 — the container maps 5433→5432 internally)
Database: audiotours
User: admin
Password: password123
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `network development_default not found` | Run `docker network create development_default` |
| `.env not found` error on `docker compose up` | Place `.env` in repo root (from USB) |
| Port 5000 in use | Check for conflicting services: `netstat -ano \| findstr :5000` |
| Build fails on COPY | Ensure you're on the `storied` branch; check `.dockerignore` exceptions |
| Postgres connection refused | Use port **5433**, not 5432 |
