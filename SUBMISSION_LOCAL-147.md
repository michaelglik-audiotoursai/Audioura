##### READY FOR REVIEW

## LOCAL-147 — Restore Newsletter Processor Service

### Commit
See `git log --oneline storied..HEAD` for hash after push.

### Summary
`newsletter_processor_service.py` was defined in the old `docker-compose.yml`
but absent from `docker-compose-master.yml` (the active stack). Per the
UNREACHED_CODE_AUDIT Rank 3, this left `spotify_processor.py`, Apple Podcasts
processing, and `content_expander.py` unreachable. Only
`newsletter-link-extractor` was running, handling link extraction only.

The code exists inside `audioura-tour-generator:latest` — same LOCAL-145
pattern. Started it from that image with no build.

### What was done

1. **Confirmed the image contains the code and all local dependencies:**
   ```
   docker exec audioura-tour-generator-1 ls /app/newsletter_processor_service.py
   /app/newsletter_processor_service.py

   docker exec audioura-tour-generator-1 ls /app/apple_podcasts_processor.py \
     /app/spotify_processor.py /app/subscription_detector.py \
     /app/dh_service_simple.py /app/content_expander.py \
     /app/advertising_url_filter.py
   # All present
   ```

2. **Identified one missing pip package** (`beautifulsoup4`). All other
   dependencies (psycopg2, flask, requests, stdlib) already installed.

3. **Started the service** via `docker run` (not compose `up`):
   ```
   docker run -d \
     --name newsletter-processor-1 \
     --network development_default \
     -p 5017:5017 \
     -e DB_HOST=postgres-2 \
     -e DB_NAME=audiotours \
     -e DB_USER=admin \
     -e DB_PASSWORD=password123 \
     -e DB_PORT=5432 \
     -e NEWS_ORCHESTRATOR_URL=http://news-orchestrator-1:5012 \
     --restart unless-stopped \
     audioura-tour-generator:latest \
     sh -c "pip install beautifulsoup4 --quiet && python newsletter_processor_service.py"
   ```

4. **Added compose entry** to `docker-compose-master.yml` for reproducibility
   (image-based, no build).

### Rollback command
```bash
docker stop newsletter-processor-1 && docker rm newsletter-processor-1
```

### Evidence

#### Health endpoint:
```
$ curl -s http://localhost:5017/health
{"service":"newsletter_processor","status":"healthy"}
```

#### Real route — GET /newsletters_v2:
```
$ curl -s http://localhost:5017/newsletters_v2
{"newsletters":[],"status":"success"}
```

#### Real route — POST /get_articles_by_newsletter_id (DB-connected, returns data):
```
$ curl -s -X POST http://localhost:5017/get_articles_by_newsletter_id \
  -H "Content-Type: application/json" -d '{"newsletter_id": 1}'
{"articles":[],"status":"success"}
```

#### Container uptimes — no existing containers disturbed:
BEFORE:
```
audioura-coordinates-fromai-1       Up 43 hours (healthy)
audioura-map-delivery-1             Up 43 hours (unhealthy)
audioura-polly-tts-1-1              Up 44 hours
audioura-tour-generation-modernized-1-1  Up 43 hours
audioura-tour-generator-1           Up 36 hours (unhealthy)
audioura-tour-id-resolution-1       Up 2 days
audioura-tour-orchestrator-1        Up 43 hours
audioura-tour-processor-1           Up 44 hours (unhealthy)
audioura-tour-update-1              Up 4 days
audioura-translation-service-1      Up 2 days
audioura-treats-1                   Up 4 days
audioura-user-api-2-1               Up 43 hours
audioura-voice-control-1            Up 4 days (unhealthy)
background-article-processor-1      Up 4 days
development-postgres-2-1            Up 4 days
news-generator-1                    Up 2 days
news-orchestrator-1                 Up 43 hours
news-processor-1                    Up 4 days
newsletter-link-extractor-1         Up 4 days
simple-news-search-1                Up 4 days
tour-editing-phase2-1               Up 21 minutes
```

AFTER:
```
[All identical uptimes — no change]
newsletter-processor-1              Up 47 seconds  (NEW)
```

#### Row counts (unchanged):
```
BEFORE: audio_tours=106, stop_metrics=1011
AFTER:  audio_tours=106, stop_metrics=1011
```

### Per-file changes
| File | Change |
|------|--------|
| `docker-compose-master.yml` | Added `newsletter-processor` service definition (image-based, no build) |
| `SUBMISSION_LOCAL-147.md` | This file |

### Limitations

1. **beautifulsoup4 installed at startup**: Same fragility as LOCAL-145's
   `boto3`. The `audioura-tour-generator:latest` image lacks `beautifulsoup4`.
   The command installs it on each container start. This adds ~10s to cold-start
   and requires PyPI to be reachable. A proper fix is to add `beautifulsoup4`
   to the image's requirements and rebuild (blocked by hung builder).

2. **Browser automation unavailable**: `spotify_processor.py` and parts of
   the newsletter processor use `browser_automation` (Selenium) for JavaScript-
   rendered pages. The `audioura-tour-generator:latest` image does not have
   Selenium or a browser installed. These code paths fail silently (wrapped in
   try/except). The service starts and handles non-browser routes, but
   Spotify browser extraction and paywalled article scraping that needs a
   headless browser will not function. Restoring that requires a build with
   a Playwright/Selenium base image — blocked.

3. **No newsletters configured**: `/newsletters_v2` returns an empty list
   because no newsletter sources are registered in the DB. The service is
   ready to process them once configured.

4. **Credential pipeline endpoints exist but full pipeline requires
   additional services** (`subscription_credentials_service.py` — Rank 2 in
   the audit) that are not deployed and not addressed here.
