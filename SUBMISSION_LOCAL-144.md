##### READY FOR REVIEW

**Task:** LOCAL-144  
**Agent:** Mac Mini Kiro  
**Branch:** kiro/local144-seam-audit  
**Base:** storied  
**Commit:** 455edf1

---

## Changes

| File | Change |
|------|--------|
| `UNREACHED_CODE_AUDIT.md` | +288 lines — full audit report |

---

## Method

Entry-point-rooted call graph traversal from all 19 services in `docker-compose-master.yml`, verified against running containers (`docker ps`). All four carriers searched:

1. **Module nobody imports:** `grep -rn "from <module>\|import <module>" *.py tests/*.py` for ~40 candidate modules
2. **Function imported but never called:** Traced import chains from each entry point through transitive dependencies
3. **Swallowed exceptions:** `grep` for `except.*pass` combined with context around `import` and `register` statements. Found 6 HIGH-risk, 3 MEDIUM-risk silent-pass patterns in production code.
4. **Blueprint/handler defined but never registered:** `grep -rn "Blueprint(" *.py` + `grep -rn "register_blueprint" *.py`. All defined Blueprints are registered. No orphan handlers found.

---

## Key Findings

### All 6 D31 instances: FIXED
Every prior known failure has production callers verified.

### 10 new wired-wrong findings (ranked):
1. **Tour editing** — entire feature not running (not in master compose, no container)
2. **Practical facts QA gate** — silently disabled via `except ImportError: pass`
3. **Walking directions** — `except (ImportError, Exception): pass` hides all failures
4. **Voice NLP service** — Dockerfile exists, never deployed
5. **Subscription credential pipeline** — 3 modules, zero deployment
6. **GCP auth token** — bare `except: pass` hides auth failures
7. **Tour hook generation** — zero imports anywhere
8. **Translation ZIP validation** — corrupt ZIPs silently pass
9. **Newsletter processor** — in old compose only, not in master
10. **Error evidence/verification tier** — silently lost via except pass

### 18+ genuinely dead modules (safe to delete)
`*_raw.py` variants, multiple `tour_editing_phase2_*.py` copies, prototype servers.

---

## Evidence

### Carrier 1 — Module nobody imports:
```
$ grep -rn "from tour_hook_generator\|import tour_hook_generator" *.py tests/*.py
(zero results)

$ grep -rn "from subscription_credentials_service\|import subscription_credentials_service" *.py tests/*.py
(zero results)

$ grep -rn "from voice_nlp_service\|import voice_nlp_service" *.py tests/*.py
(zero results)
```

### Carrier 3 — Swallowed exception:
```
generate_tour_text.py:6449:
    try:
        from directions_generator import generate_walking_directions
        ...
    except (ImportError, Exception):
        pass

content_qa_runner.py:760:
    try:
        from practical_facts_gate import extract_practical_claims as _extract_pf
        ...
    except ImportError:
        pass

tour_generation_modernized.py:40:
    try:
        ...
        resp = requests.get(f"http://metadata.google.internal/...")
    except:
        pass
```

### Carrier 4 — All Blueprints registered:
```
$ grep -rn "Blueprint(" *.py
sharing_endpoints.py:23:sharing_bp = Blueprint('sharing', __name__)
referral_endpoints.py:30:referral_bp = Blueprint('referral', __name__)
persona_endpoints.py:20:persona_bp = Blueprint('persona', __name__)
deeplink_resolution_endpoint.py:17:deeplink_bp = Blueprint('deeplink', __name__)

$ grep -rn "register_blueprint" *.py
generate_tour_text_service.py:59:app.register_blueprint(sharing_bp)
generate_tour_text_service.py:63:app.register_blueprint(referral_bp)
generate_tour_text_service.py:67:app.register_blueprint(persona_bp)
tour_id_resolution_service.py:29:app.register_blueprint(deeplink_bp)
```
All matched — no orphan Blueprints.

### Docker ps (verifying what runs):
```
$ docker ps --format "{{.Names}}" | sort
audioura-coordinates-fromai-1
audioura-map-delivery-1
audioura-polly-tts-1-1
audioura-tour-generation-modernized-1-1
audioura-tour-generator-1
audioura-tour-id-resolution-1
audioura-tour-orchestrator-1
audioura-tour-processor-1
audioura-tour-update-1
audioura-translation-service-1
audioura-treats-1
audioura-user-api-2-1
audioura-voice-control-1
background-article-processor-1
development-postgres-2-1
news-generator-1
news-orchestrator-1
news-processor-1
newsletter-link-extractor-1
simple-news-search-1
```
No tour-editing, newsletter-processor, or voice-nlp containers.

---

## Limitations

1. Cloud Run deployments (`tour_worker_service.py`, `Dockerfile.cloudrun`) not auditable from Docker host
2. Dynamic dispatch (`importlib`, `getattr`) not observed but cannot be ruled out
3. Flutter/Dart mobile dead code not audited
4. Conditional `try/except` imports classified as "wired-wrong" rather than strictly "unreachable" — they DO execute in the happy path
5. Inter-service HTTP call targets not exhaustively validated (only tour-editing confirmed dead)
6. The old `docker-compose.yml` defines services the master compose omits — if anyone runs the old compose, those services come alive
