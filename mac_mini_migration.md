# Mac Mini Migration — Development Environment Setup

## Context
Michael's Windows laptop is at the repair center. The Mac Mini is the only available development machine. All source code is on GitHub (`origin/storied` branch). This document directs Kiro on the Mac Mini to set up the full Audioura/Storied development environment.

## Repository
- **Remote**: `https://github.com/michaelglik-audiotoursai/Audioura.git`
- **Branch**: `storied`
- **Latest commit**: `078b52d` (all code, docs, pilots, and fixtures are pushed)

---

## Step 1: Prerequisites (install if not present)

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Git (usually pre-installed on macOS, verify)
git --version || xcode-select --install

# Python 3.10+
brew install python@3.13

# Docker Desktop for Mac
# Download from: https://www.docker.com/products/docker-desktop/
# Install the .dmg, launch Docker Desktop, ensure it's running

# Verify Docker
docker --version
docker-compose --version
```

## Step 2: Clone the repository

```bash
cd ~/eclipse-workspace   # or wherever Michael prefers
git clone https://github.com/michaelglik-audiotoursai/Audioura.git
cd Audioura/development
git checkout storied
git log --oneline -3  # verify latest is 078b52d
```

## Step 3: Environment variables

Create `.env` in the `development/` directory with these keys (get from Michael):

```bash
# Required API keys
OPENAI_API_KEY=sk-...
SERP_API_KEY=...
STORIED_MODE=true
GENERATION_TIER=plus

# Database (local Docker Postgres)
DATABASE_URL=postgresql://admin:password123@localhost:5432/audiotours
VENUE_CACHE_DB_URL=postgresql://admin:password123@localhost:5432/audiotours
```

## Step 4: Build and start Docker services

```bash
cd ~/eclipse-workspace/Audioura/development

# Build the tour-generator container
docker-compose -f docker-compose-master.yml build tour-generator

# Start all services (tour-generator + postgres)
docker-compose -f docker-compose-master.yml up -d

# Verify containers are running
docker ps | grep -E "tour-generator|postgres"

# Verify tour-generator health
curl http://localhost:5000/health
```

### Potential macOS Docker adjustments:
- If `docker-compose-master.yml` has Windows-style volume paths (e.g., `C:\...`), they need to be adjusted to Unix paths or removed (the Dockerfile copies source into the image, so bind mounts may not be needed)
- If Postgres uses a named volume, it should work as-is
- The container's internal DB connection uses `postgres-2` hostname — this is resolved within the Docker network, no change needed

## Step 5: Run test suites (verify environment works)

```bash
cd ~/eclipse-workspace/Audioura/development

# All regression suites must pass
python3 test_sq4_merge.py
python3 test_f4_cache_roundtrip.py
python3 test_w7_wiring.py
python3 test_b6_generation_wiring.py
python3 test_w9_collection_anchor.py
python3 test_palais_fix_lead_fixture.py
```

Expected: ALL TESTS PASSED on each suite.

## Step 6: Verify tour generation works end-to-end

```bash
# Run a test generation inside the container
docker exec development-tour-generator-1 python -c "
import sys, os
sys.path.insert(0, '/app')
os.environ['STORIED_MODE'] = 'true'
from generate_tour_text import generate_tour_text
text, _, coords = generate_tour_text('Palais Lascaris, Nice, France', 'museum', '/tmp/test.txt', 6)
print(f'SUCCESS: {len(text)} chars' if text else 'FAILED')
"
```

Expected: `SUCCESS: ~10000+ chars`

---

## Current Task Queue (as of 2026-07-14)

| Priority | Task | Status |
|----------|------|--------|
| HIGH | `wdvrdawkxp` — PALAIS-FIX hardening | In progress (B1–B4 submitted, awaiting LEAD review) |
| HIGH | `wdvrdawkxq` — External listings design | To do (sequenced after PALAIS-FIX, approach comment needed) |
| URGENT | `wdvrdawcyx` — Generic Grounding | In progress (Phase 3 after SQ4 closes) |
| HIGH | `wdvrdawdje` — Story Quality | SQ4 CLOSED by LEAD |

## Key Files

| File | Purpose |
|------|---------|
| `generate_tour_text.py` | Main tour generation pipeline |
| `generate_tour_text_service.py` | Flask service wrapper + QA + i-con |
| `story_element_extractor.py` | SQ element extraction + scoring + W9 anchoring |
| `work_story_searcher.py` | SERP search + source tier classification |
| `remind_Services_ai.md` | Services Kiro context/identity file |
| `docker-compose-master.yml` | Docker service definitions |

## Git Workflow Rules (from remind_Services_ai.md)

- **Branch**: `storied` (off `main` = `beta-2.1.1+18`). **Never touch `main`.**
- **VERSION**: `2.2.0+1`
- **One task = one commit = one review**
- **Pilot as CHILD commit** (code_sha == HEAD)
- **Never claim PASS without running the actual check**

## ClickUp Integration

The ClickUp MCP server should be configured in Kiro's MCP settings on the Mac Mini. The task list ID is `1000410000000733` (🟦 Services — Kiro).

---

## Summary

Once Steps 1–6 complete successfully, the Mac Mini is a fully functional development environment identical to the Windows laptop. All Docker services, Python tests, and the generation pipeline will work the same way. The only difference is the host OS paths — everything inside Docker is Linux regardless.
