# Unreached Code Audit — LOCAL-144

**Date:** 2026-08-02  
**Auditor:** Mac Mini Kiro  
**Base:** storied (commit e609720)

---

## Method

**Entry points identified from `docker-compose-master.yml` (the active compose — verified against `docker ps`):**

| Container | Entry Point File | Port |
|-----------|-----------------|------|
| tour-generator | `generate_tour_text_service.py` | 5000 |
| tour-orchestrator | `tour_orchestrator_service.py` | 5002 |
| tour-processor | `tour_generation_service.py` | 5001 |
| tour-generation-modernized-1 | `tour_generation_modernized.py` | 5021 |
| polly-tts-1 | `polly_tts_service.py` | 5018 |
| translation-service | `translation-service/translation_service.py` | 5030 |
| user-api-2 | `user-tracking/app.py` | 5003 |
| tour-update | `tour-update-service/app.py` | 5004 |
| coordinates-fromai | `coordinates_fromAI/app.py` | 5006 |
| map-delivery | `map_delivery/app.py` | 5005 |
| treats | `treats_service.py` (COPY'd as app.py) | 5007 |
| voice-control | `voice_control/app.py` | 5008 |
| news-generator-1 | `news_generator_service.py` | 5010 |
| news-processor-1 | `news_processor_service.py` | 5011 |
| news-orchestrator-1 | `news_orchestrator_service.py` | 5012 |
| newsletter-link-extractor | `newsletter_link_extractor_service.py` | 5014 |
| background-article-processor | `background_article_processor_service.py` | 5015 |
| simple-news-search | `simple_news_search_service.py` | 5016 |
| tour-id-resolution | `tour_id_resolution_service.py` | 5025 |

**Additional entry points:** `kiro_dispatcher.py` (dev automation, `__main__`), `tour_worker_service.py` (Cloud Run target, not Docker).

**Carriers searched:**
1. Module nobody imports → grep `from <module>` / `import <module>` across all .py files
2. Function imported but never called → traced import chains from entry points
3. Swallowed exceptions → grep for `except.*:.*pass` around imports and registrations
4. Blueprint/handler defined but never registered → grep `Blueprint(` and `register_blueprint`

**What this method would miss:**
- String-based dispatch (`getattr`, dynamic imports via `importlib`)
- Code reachable only through Cloud Run deployments not represented in docker-compose-master.yml
- Dead code WITHIN a reachable module (unreachable branches inside a function that IS called)
- Flutter/Dart dead code (not audited)

---

## Re-verification of the Six Known D31 Instances

| # | Instance | Current Status | Evidence |
|---|----------|---------------|----------|
| 1 | story_element_extractor.py — zero callers | ✅ FIXED | Called from `generate_tour_text.py:4646,4867,5367` |
| 2 | corpus mining — swallowed ImportError | ✅ FIXED | `tour_orchestrator_service.py:119-125` now logs at ERROR with context message |
| 3 | check_cost_ceiling — no callers | ✅ FIXED | Renamed to `enforce_cost_ceiling`, called from `generate_tour_text_service.py:213` |
| 4 | Subscribed — no glue | ✅ FIXED | Entitlements, cost_meter, etc. all have production callers now |
| 5 | register_preference_routes — never called | ✅ FIXED | Called at `tour_orchestrator_service.py:121` at startup |
| 6 | TestTourFactory — only self-test callers | ✅ FIXED | Used in 8+ test files (LOCAL-139/141 migrated suites); test infrastructure doesn't need production callers |

**All six resolved.** The register_preference_routes fix wraps the call in try/except that logs at ERROR — acceptable given the alternative (service crash on import failure).

---

## Findings — Wired-Wrong Code (feature that should work and does not)

### RANK 1 (HIGH IMPACT): Tour Editing — entire feature silently not running

**Modules:** `tour_editing_phase2.py`, `tour_editing_simple.py`, `tour_editing_service.py`  
**Why unreachable:** Defined in `docker-compose.yml` (the old dev compose) but NOT in `docker-compose-master.yml` (the active production compose). No container is running for ports 5020 or 5022. Verified: `docker ps` shows no editing container.

**Feature silently not working:** Users cannot edit individual tour stops after generation. The mobile app references port 5022 (`lib/services/tour_editing_service.dart` routes to `/tour-editing`). Every edit request from the app either 404s or times out silently. The Phase 2 service includes Polly TTS regeneration, custom audio upload, async job processing — none of it executes.

**Carrier:** Module is defined but never deployed (variant of carrier #1 — the service exists, the compose doesn't start it).

---

### RANK 2 (HIGH IMPACT): Practical facts QA gate silently disabled

**Location:** `content_qa_runner.py:760`  
```python
try:
    from practical_facts_gate import extract_practical_claims as _extract_pf
    ...
except ImportError:
    pass
```

**Why unreachable:** While `practical_facts_gate.py` exists and IS imported by `generate_tour_text.py:6676` (production path), the QA runner's copy at line 760 silently falls through if the import fails for ANY reason (module present but broken, wrong directory context, etc.). More critically: `content_qa_runner.py` itself is imported by `generate_tour_text_service.py:245` inside a try/except — if content_qa_runner fails to load (any syntax error, missing dep), the ENTIRE QA pipeline disappears silently.

**Feature silently not working:** Tours with incorrect opening hours, wrong prices, or fabricated practical information ship without QA checking. The QA gate was designed to catch these after LOCAL-36.

**Carrier:** Swallowed exception (carrier #3).

---

### RANK 3 (HIGH IMPACT): Walking directions silently disabled

**Location:** `generate_tour_text.py:6449`  
```python
try:
    from directions_generator import generate_walking_directions
    ...
except (ImportError, Exception):
    pass
```

**Why unreachable:** The `except (ImportError, Exception): pass` catches literally EVERY error including bugs in `directions_generator.py` itself. If `directions_generator` has a runtime bug, walking directions silently disappear from all tours without any log entry.

**Feature silently not working:** Walking tours lose turn-by-turn navigation directions between stops. Users get no walking guidance. This has the "corpus mining" profile — works in dev, silently fails in production if any dependency (Google Maps API, etc.) is misconfigured.

**Carrier:** Swallowed exception (carrier #3).

---

### RANK 4 (HIGH IMPACT): Voice NLP service — Dockerfile exists, never deployed

**Module:** `voice_nlp_service.py`  
**Why unreachable:** Has `Dockerfile.voice-nlp` but appears in NO docker-compose file. Zero containers run it. Zero modules import it.

**Feature silently not working:** The `/generate_short_title` endpoint (AI-shortened article titles for the news system) is unavailable. Any service attempting to call it gets connection refused. The news system presumably falls back to truncated titles or skips title shortening entirely.

**Carrier:** Module nobody imports AND never deployed (carriers #1 + #4 combined).

---

### RANK 5 (MEDIUM-HIGH): Subscription credential pipeline — three orphan modules

**Modules:**
- `subscription_credentials_service.py` — Flask endpoint for credential submission (zero imports, no Dockerfile, no compose entry)
- `diffie_hellman_service.py` — DH key exchange for secure credential transport (only imported by test)
- `subscription_article_processor.py` — browser automation for paywalled articles (only imported by tests)

**Why unreachable:** None of these are in any docker-compose file. None are imported by any running service. The mobile app's Diffie-Hellman handshake has no server to connect to.

**Feature silently not working:** The "Subscribed" tier's credential storage pipeline. Users who pay for Unlimited ($50/month) cannot submit newspaper credentials, so paywalled article access doesn't work. The mobile DH code sends a public key to an endpoint that doesn't exist. D4 (cost stop → "offer Pay-Per-Use switch") depends on this working.

**Carrier:** Module nobody imports (carrier #1). Three modules form a pipeline with zero deployment.

---

### RANK 6 (MEDIUM-HIGH): GCP auth token silently fails — bare `except:`

**Location:** `tour_generation_modernized.py:40`  
```python
try:
    ...
    resp = requests.get(
        f"http://metadata.google.internal/computeMetadata/v1/instance/...",
        headers={"Metadata-Flavor": "Google"}, timeout=5)
    if resp.status_code == 200:
        return {"Authorization": f"Bearer {resp.text}"}
except:
    pass
```

**Why unreachable:** Bare `except: pass` — any failure in GCP metadata retrieval (wrong URL, timeout, DNS error) is swallowed. In a local Docker deployment, this ALWAYS fails silently since there's no GCP metadata service.

**Feature silently not working:** Service-to-service authentication on Cloud Run. When deployed to GCP, if the metadata endpoint changes or has a transient error, inter-service calls proceed without auth tokens, getting 403 responses that look like business logic bugs rather than auth failures. Locally: not relevant (expected to fail).

**Carrier:** Swallowed exception (carrier #3). The bare `except:` is the most dangerous variant.

---

### RANK 7 (MEDIUM): Tour hook generation — orphan module

**Module:** `tour_hook_generator.py`  
**Why unreachable:** Zero imports anywhere in the codebase. Not even test files import it.

**Feature silently not working:** Tour introductions (the 40-60 word hook that plays before stop 1) are not generated. Tours either have no spoken introduction or use whatever fallback the generation pipeline provides. Task S37 specified this feature.

**Carrier:** Module nobody imports (carrier #1).

---

### RANK 8 (MEDIUM): Translation service ZIP validation — swallowed exception

**Location:** `translation-service/translation_service.py:252`  
```python
try:
    ...
    with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as _z:
        audio_files_in_zip = [n for n in _z.namelist() if ...]
    if not audio_files_in_zip:
        logging.error(...)
        return None, False
except Exception:
    pass
```

**Why unreachable:** If the ZIP is corrupt (invalid header, truncated bytes), the `except Exception: pass` swallows the error and translation continues with broken/empty data. The error-logging path inside the try block (no audio files) never fires because the exception occurs before that check.

**Feature silently not working:** Corrupt tour ZIPs silently produce broken translations. Users requesting a translated tour get incomplete output with no audio files. The service appears to succeed (200 response) but delivers garbage.

**Carrier:** Swallowed exception (carrier #3).

---

### RANK 9 (MEDIUM): Newsletter processor service — deployed in old compose only

**Module:** `newsletter_processor_service.py`  
**Why unreachable:** In `docker-compose.yml` (old dev compose) but NOT in `docker-compose-master.yml` (active compose). `docker ps` confirms no `newsletter-processor-1` container running. Two dedicated Dockerfiles (`Dockerfile.newsletter-processor`, `Dockerfile.newsletter-browser`) are never referenced by any compose file.

**Feature silently not working:** Spotify podcast processing (`spotify_processor.py`), Apple Podcasts processing, browser-automated article extraction, and credential-based paywalled content access. The `newsletter-link-extractor` service (which IS running) handles link extraction but cannot do the heavy browser-based processing that `newsletter_processor_service.py` provides.

**Downstream impact:** `content_expander.py` is only reachable through `spotify_processor.py` → `newsletter_processor_service.py`. If newsletter-processor doesn't run, content expansion for podcast sources is dead.

**Carrier:** Module deployed in wrong compose file (variant of carrier #1).

---

### RANK 10 (LOW-MEDIUM): Error evidence and verification tier silently lost

**Locations:**
- `generate_tour_text_service.py:168` — `_LAST_CLEAN_FAIL_EVIDENCE` import, `except (ImportError, AttributeError): pass`
- `generate_tour_text_service.py:281` — `_LAST_VERIFICATION_TIER` import, `except (ImportError, AttributeError): pass`
- `generate_tour_text_service.py:384` — `_LAST_POI_LIST` verification flags, `except (ImportError, AttributeError): pass`

**Feature silently not working:** When these fail: (a) debugging tour generation failures becomes impossible because error evidence is lost, (b) verification tier metadata is missing from API responses, (c) stop-level "verified" flags never get set so quality metrics report everything as unverified.

**Carrier:** Swallowed exception (carrier #3).

---

## Findings — Genuinely Dead Code (safe to delete, no feature lost)

| Module | Why Dead | Safe to Delete? |
|--------|----------|----------------|
| `poi_inclusion_exceptions_raw.py` | Never imported anywhere. Superseded by `poi_inclusion_exceptions.py` (which IS used). | Yes |
| `enhanced_tour_templates.py` | Never imported. Superseded by `enhanced_tour_templates_fixed.py`. | Yes |
| `enhanced_tour_templates_fixed_raw.py` | Never imported anywhere. Intermediate draft. | Yes |
| `tour_type_detector_raw.py` | Never imported. Superseded by `tour_type_detector.py`. | Yes |
| `tour_settings_raw.py` | Never imported. Superseded by `tour_settings.py`. | Yes |
| `enhanced_prompt_generator_raw.py` | Never imported. Superseded by `enhanced_prompt_generator.py`. | Yes |
| `poi_inclusion_exceptions_raw.py` | Never imported. Draft predecessor. | Yes |
| `tour_editing_phase2_final.py` | Never imported. Variant of tour_editing_phase2.py. | Yes |
| `tour_editing_phase2_complete.py` | Never imported. Variant. | Yes |
| `tour_editing_phase2_container.py` | Never imported. Variant. | Yes |
| `tour_editing_service.py` | Never imported. Superseded by tour_editing_simple.py. | Yes |
| `tour_rubric_scorer.py` | Never imported. Manual scoring tool, never integrated. | Yes (or move to tools/) |
| `simple_api_server.py` / `simple_api.py` | Never imported. Prototype/debug servers. | Yes |
| `version_api.py` | Never imported. Functionality exists in main services. | Yes |
| `content_extraction.py` | Only imported by a test file. No production path. | Yes (after reviewing test) |
| `newsletter_utils.py` | Only imported by `content_extraction.py` (itself dead). | Yes |
| `score_local100_strict.py` | Never imported. One-off scoring script. | Move to tools/ |
| `map_delivery_service.py` (root) | NOT in master compose. Root copy (952 lines) vs `map_delivery/app.py` (362 lines, the one actually deployed). Old version. | Yes — but verify no env uses it |

---

## Commands Used

```bash
# Carrier 1: Module nobody imports
grep -rn "from <module_name>\|import <module_name>" *.py tests/*.py

# Carrier 2: Function imported but never called
# Traced from entry points through import chains manually

# Carrier 3: Swallowed exceptions
grep -rn "except.*:" *.py | grep -A2 "pass"
# Combined with context around import statements

# Carrier 4: Blueprint/handler defined but never registered
grep -rn "Blueprint(" *.py
grep -rn "register_blueprint" *.py
grep -rn "register_.*routes" *.py

# Entry point verification
docker ps --format "table {{.Names}}\t{{.Ports}}"
cat docker-compose-master.yml
```

---

## Limitations and False-Negative Risk

1. **Cloud Run paths not audited:** `tour_worker_service.py` and `Dockerfile.cloudrun` define Cloud Run deployments. Code reachable only through Cloud Run is invisible to this docker-compose-rooted analysis.

2. **Dynamic dispatch:** If any service uses `importlib.import_module()` or `getattr()` to load modules by string name, this audit will miss those paths. No such pattern was observed, but I did not exhaustively verify.

3. **Conditional try/except imports:** Many modules are imported inside `try/except` blocks in `generate_tour_text.py`. They ARE reachable in the happy path but degrade silently to nothing if the module has any issue. I classified the worst ones as "wired-wrong" rather than "unreachable" — the distinction is subtle.

4. **Flutter/Dart code:** The mobile app's dead code was not audited. The task file mentions `tour_editing_service.dart` routing to port 5022 — if the backend isn't running, the mobile code is effectively dead too.

5. **`docker-compose.yml` vs `docker-compose-master.yml`:** The old `docker-compose.yml` defines services (tour-editing, newsletter-processor) that the master compose omits. If someone runs `docker-compose up` instead of `docker-compose -f docker-compose-master.yml up`, those services WOULD run. I classified based on what is ACTUALLY running (`docker ps`).

6. **Inter-service HTTP calls:** If Service A calls Service B at a URL that doesn't resolve (because B isn't running), that call path is effectively dead. I found tour-editing (rank 1) this way but may have missed others where a running service makes HTTP calls to non-running services.
