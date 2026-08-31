# Audio Tours AI

AI-powered audio tour generator with mobile app for Android and iOS.

## Project Structure

```
├── *.py                    # Python backend services (10 microservices)
│   ├── tour_orchestrator_service.py    # Main orchestration (port 5002)
│   ├── generate_tour_text_service.py   # Tour text generation (port 5000)
│   ├── tour_generation_service.py      # Tour processing (port 5001)
│   ├── voice_control_service.py        # Voice control (port 5008)
│   ├── map_delivery_service.py         # Map delivery (port 5005)
│   ├── treats_service.py               # Treats service (port 5007)
│   ├── coordinates_fromai_service.py   # Coordinates AI (port 5006)
│   ├── tour_delivery_service.py        # Tour update (port 5004)
│   ├── [user_api_service.py]           # User API (port 5003)
│   └── docker-compose.yml             # Docker services + PostgreSQL
├── audio_tour_app/         # Flutter mobile application
│   ├── lib/                # Dart source code
│   ├── android/            # Android-specific files
│   ├── ios/                # iOS-specific files
│   └── pubspec.yaml        # Flutter dependencies
└── tours/                  # Generated tour files
```

## Quick Start

### Server (Backend - 10 Microservices)
```bash
docker-compose -f docker-compose-beta-local.yml up -d
```

> ⚠️ **Do not run a bare `docker-compose up -d`.** Two reasons, both real:
>
> 1. **`docker-compose.yml` cannot build anything.** It declares `build: .` for 14
>    services, and there is no root `Dockerfile` — it was removed and the compose file
>    was never updated. Verified 2026-08-31.
> 2. **It can destroy unrelated containers.** Several long-running containers on the
>    development machines share names with services here. A bare `up` collides on those
>    names and offers `--remove-orphans`; accepting it deletes them.
>
> Use `docker-compose-beta-local.yml`, which builds from each service's own repaired
> Dockerfile and brings up 21 healthy services. Requires `OPENAI_API_KEY` in `.env`.
> Full recipe: ClickUp [`wdvrdaxn8x`](https://app.clickup.com/t/wdvrdaxn8x).

**Services:**
- **tour-orchestrator** (5002) - Main orchestration
- **tour-generator** (5000) - Tour text generation  
- **tour-processor** (5001) - Tour processing
- **voice-control** (5008) - Voice control
- **map-delivery** (5005) - Map delivery
- **treats** (5007) - Treats service
- **coordinates-fromai** (5006) - Coordinates AI
- **tour-update** (5004) - Tour updates
- **user-api-2** (5003) - User API
- **postgres-2** (5432) - PostgreSQL database

### Flutter App
```bash
cd audio_tour_app
flutter pub get
flutter run
```

## Building APK

The project uses GitHub Actions for automated APK building on Linux (resolves Windows compatibility issues with speech_to_text).

Push to main branch → GitHub Actions builds APK → Download from Actions tab

## Voice Recognition

Uses speech_to_text package with volume button activation for offline voice commands:
- Triple-press volume buttons → Voice listening activated
- Supports commands: "Play", "Pause", "Next", "Previous", "Repeat", etc.