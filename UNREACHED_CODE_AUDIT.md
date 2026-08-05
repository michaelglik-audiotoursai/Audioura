# Unreached Code Audit — LOCAL-144

**Date:** 2026-08-02 (revised round 2)  
**Auditor:** Mac Mini Kiro  
**Base:** storied (commit e609720)

---

## Method

**Entry points identified from `docker-compose-master.yml` (the active compose):**

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
1. Module nobody imports → `grep -rn "from <module>\|import <module>" *.py */*.py` for each candidate
2. Function imported but never called → traced import chains from entry points
3. Swallowed exceptions → grep + actual import verification (see table below)
4. Blueprint/handler defined but never registered → `grep -rn "Blueprint(" *.py` + `grep -rn "register_blueprint\|register.*routes" *.py`

**Verification method for imports:** Each swallowed-exception location was tested by running `python3 -c "from <module> import <symbol>"` from the repo root, reproducing the import as the container would execute it. Results are marked IMPORTS-OK or IMPORTS-FAIL.

**What this method would miss:**
- String-based dispatch (`getattr`, dynamic imports via `importlib`)
- Code reachable only through Cloud Run deployments not represented in docker-compose-master.yml
- Dead code WITHIN a reachable module (unreachable branches inside a function that IS called)
- Flutter/Dart dead code (not audited — except where it calls non-existent backends)
- Inter-service HTTP calls to non-running services (found tour-editing this way, may have missed others)

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

## Category A — Wired-Wrong Code (feature that should work and does not)

### RANK 1 (HIGH IMPACT): Tour Editing — entire feature silently not running

**Modules:** `tour_editing_phase2.py`, `tour_editing_simple.py`  
**Why unreachable:** Defined in `docker-compose.yml` (the old dev compose) but NOT in `docker-compose-master.yml` (the active production compose). No container is running for ports 5020 or 5022.  
**Verified by:** `grep -i "tour.edit\|5020\|5022" docker-compose-master.yml` → zero matches; `grep` on `docker-compose.yml` → present.  
**Evidence RAN:** Yes — grep against both compose files.

**Feature silently not working:** Users cannot edit individual tour stops after generation. The mobile app at `lib/config/endpoints.dart:30` maps `Service.tourEditing: 5022`, and `edit_stop_screen.dart` + `edit_tour_screen.dart` both import `tour_editing_service.dart`. Every edit request from the app either times out or connection-refuses. The Phase 2 service includes Polly TTS regeneration, custom audio upload, async job processing — none of it executes.

**Carrier:** Module deployed in wrong compose file (carrier #1 variant — service exists, master compose doesn't start it).

---

### RANK 2 (HIGH IMPACT): Subscription credential pipeline — three orphan modules, no deployment

**Modules:**
- `subscription_credentials_service.py` — Flask endpoint for credential submission (zero imports, no Dockerfile, no compose entry)
- `diffie_hellman_service.py` — DH key exchange for secure credential transport (zero production imports)
- `subscription_article_processor.py` — browser automation for paywalled articles (zero production imports)

**Why unreachable:** None appear in any docker-compose file. `grep -rn "from subscription_credentials\|import subscription_credentials\|from diffie_hellman\|import diffie_hellman\|from subscription_article\|import subscription_article" *.py */*.py` (excluding tests) → zero matches.  
**Evidence RAN:** Yes — grep for imports returned empty.

**Feature silently not working:** The "Subscribed" tier's credential storage pipeline. Users who pay for Unlimited ($50/month) cannot submit newspaper credentials, so paywalled article access doesn't work. The mobile app's Diffie-Hellman handshake sends a public key to an endpoint that doesn't exist.

**Carrier:** Module nobody imports (carrier #1). Three modules form a pipeline with zero deployment.

---

### RANK 3 (MEDIUM-HIGH): Newsletter processor — deployed in old compose only

**Module:** `newsletter_processor_service.py`  
**Why unreachable:** In `docker-compose.yml` (old dev compose) but NOT in `docker-compose-master.yml`. `grep -i "newsletter.processor" docker-compose-master.yml` → zero matches.  
**Evidence RAN:** Yes — grep against master compose returned empty.

**Feature silently not working:** Browser-automated article extraction, Spotify podcast processing (`spotify_processor.py`), Apple Podcasts processing, and credential-based paywalled content access. The `newsletter-link-extractor` service (which IS running) handles link extraction but cannot do the heavy browser-based processing. Downstream: `content_expander.py` is only reachable through this service.

**Carrier:** Module deployed in wrong compose file (carrier #1 variant).

---

### RANK 4 (MEDIUM): Translation service ZIP validation — corrupt ZIPs silently pass

**Location:** `translation-service/translation_service.py:252`  
```python
try:
    import io as _io
    zip_bytes = original_zip_data.tobytes() if hasattr(original_zip_data, 'tobytes') else bytes(original_zip_data)
    with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as _z:
        audio_files_in_zip = [n for n in _z.namelist() if n.startswith('audio_') and n.endswith('.mp3')]
    if not audio_files_in_zip:
        logging.error(...)
        return None, False
except Exception:
    pass
```

**Why dangerous:** If the ZIP is corrupt (invalid header, truncated bytes), the `except Exception: pass` swallows the error and translation continues with broken/empty data. The error-logging path inside the try (no audio files) never fires because the exception occurs before that check.  
**Import status:** `io` and `zipfile` are stdlib — IMPORTS-OK. The danger is runtime corruption, not import failure.  
**Evidence RAN:** Yes — import verified; impact is READ from code logic (corrupt ZIP → exception → pass → continues with garbage).

**Feature silently not working:** Corrupt tour ZIPs silently produce broken translations. Users requesting a translated tour get incomplete output with no audio files. The service appears to succeed (200 response) but delivers garbage.

**Carrier:** Swallowed exception (carrier #3). Not an import issue — a runtime error handler that discards the error.

---

## Category B — Works Today, Fails Silently Tomorrow (alarm disconnected)

These features currently work — verified by actual import. But their failure path is a bare `except: pass` or `except (ImportError, Exception): pass`, meaning the day they break (dependency issue, code bug, API change), they vanish from tours with zero log output. The alarm is disconnected.

### B-1: Practical facts QA gate

**Location:** `content_qa_runner.py:760`  
```python
try:
    from practical_facts_gate import extract_practical_claims as _extract_pf
    _pf_claims = _extract_pf(tour_text)
    ...
except ImportError:
    pass
except Exception:
    pass
```

**Import status:** `practical_facts_gate` → **IMPORTS-OK**, `extract_practical_claims` callable: **True**  
**Tested by:** `python3 -c "from practical_facts_gate import extract_practical_claims; print('OK')"`  
**Today:** Works. Practical facts are audited in QA output.  
**Tomorrow risk:** If `practical_facts_gate.py` acquires any bug (syntax error, missing dep, API change), practical-claim auditing silently disappears from QA reports. No log line, no metric change — the gate just stops firing.  
**Note:** The wrapper (`content_qa_runner` itself) is imported at `generate_tour_text_service.py:245` WITHOUT try/except — so if `content_qa_runner.py` itself breaks, tour generation fails visibly. The silent path is only the inner `practical_facts_gate` import.

---

### B-2: Walking directions generation

**Location:** `generate_tour_text.py:6449`  
```python
try:
    from directions_generator import generate_walking_directions
    _storied_directions = generate_walking_directions(poi_name, next_poi['name'], location, api_key)
    if _storied_directions:
        directions = _storied_directions
except (ImportError, Exception):
    pass
```

**Import status:** `directions_generator` → **IMPORTS-OK**, `generate_walking_directions` callable: **True**  
**Tested by:** `python3 -c "from directions_generator import generate_walking_directions; print('OK')"`  
**Today:** Works. Walking directions are generated for storied walking tours.  
**Tomorrow risk:** `except (ImportError, Exception)` catches literally every error. If `directions_generator` has a runtime bug (bad API response, malformed data, timeout handling issue), walking directions silently disappear from all tours without any log entry. Tours fall back to generic "Continue to X" transitions — a degradation users would notice but devs would not.

---

### B-3: Error evidence and verification tier metadata

**Locations:**
- `generate_tour_text_service.py:168` — `_LAST_CLEAN_FAIL_EVIDENCE`, `except (ImportError, AttributeError): pass`
- `generate_tour_text_service.py:281` — `_LAST_VERIFICATION_TIER`, `except (ImportError, AttributeError): pass`
- `generate_tour_text_service.py:384` — `_LAST_POI_LIST`, `except (ImportError, AttributeError): pass`

**Import status:** All three symbols → **IMPORTS-OK**  
**Tested by:** `python3 -c "from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE, _LAST_VERIFICATION_TIER, _LAST_POI_LIST; print('OK')"`  
**Today:** Works. Error evidence, tier metadata, and verified flags are populated.  
**Tomorrow risk:** These access module-level mutable state set during generation. If the upstream variable is renamed, removed, or changes type, the metadata silently disappears from API responses. Debugging tour generation failures becomes harder (evidence lost), quality metrics report everything as unverified.  
**Severity note:** Lower than B-1/B-2 because these are metadata/debugging aids, not user-facing features.

---

### B-4: GCP auth token — bare `except:` in Cloud Run path

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
return {}
```

**Import status:** `urllib.parse` → **IMPORTS-OK** (stdlib). The except catches network errors, not import errors.  
**Today:** In Docker on Mac, this always fails silently (no GCP metadata server) and returns `{}` — expected and harmless locally. On Cloud Run, it would succeed.  
**Tomorrow risk:** On Cloud Run, if the metadata endpoint changes URL, has a transient error, or the token format changes, inter-service calls proceed without auth tokens — getting 403s that look like business logic bugs. The bare `except:` (no even `Exception`) catches `SystemExit` and `KeyboardInterrupt` too.  
**Severity note:** Only affects Cloud Run deployment, not local Docker. Impact contingent on GCP deployment being active.

---

## Category C — Genuinely Dead Code (safe to delete, no feature lost)

| Module | Why Dead | Notes |
|--------|----------|-------|
| `poi_inclusion_exceptions_raw.py` | Never imported anywhere. Superseded by `poi_inclusion_exceptions.py` (which IS used). | Safe to delete |
| `enhanced_tour_templates.py` | Never imported. Superseded by `enhanced_tour_templates_fixed.py`. | Safe to delete |
| `enhanced_tour_templates_fixed_raw.py` | Never imported anywhere. Intermediate draft. | Safe to delete |
| `tour_type_detector_raw.py` | Never imported. Superseded by `tour_type_detector.py`. | Safe to delete |
| `tour_settings_raw.py` | Never imported. Superseded by `tour_settings.py`. | Safe to delete |
| `enhanced_prompt_generator_raw.py` | Never imported. Superseded by `enhanced_prompt_generator.py`. | Safe to delete |
| `tour_editing_phase2_final.py` | Never imported. Variant of tour_editing_phase2.py. | Safe to delete |
| `tour_editing_phase2_complete.py` | Never imported. Variant. | Safe to delete |
| `tour_editing_phase2_container.py` | Never imported. Variant. | Safe to delete |
| `tour_editing_service.py` | Never imported by production code. Superseded by `tour_editing_simple.py`. | Safe to delete |
| `tour_hook_generator.py` | Never imported. Feature implemented inline at `generate_tour_text.py:6087-6160` (prolog generation). | Safe to delete |
| `voice_nlp_service.py` | Never imported, not deployed. Feature (`/generate_short_title`) provided by `voice_control/app.py:98`. | Safe to delete |
| `tour_rubric_scorer.py` | Never imported. Manual scoring tool, never integrated. | Move to tools/ |
| `simple_api_server.py` / `simple_api.py` | Never imported. Prototype/debug servers. | Safe to delete |
| `version_api.py` | Never imported. Functionality exists in main services. | Safe to delete |
| `content_extraction.py` | Only imported by a test file. No production path. | Safe to delete (after reviewing test) |
| `newsletter_utils.py` | Only imported by `content_extraction.py` (itself dead). | Safe to delete |
| `score_local100_strict.py` | Never imported. One-off scoring script. | Move to tools/ |
| `map_delivery_service.py` (root) | NOT in master compose. Root copy (952 lines) vs `map_delivery/app.py` (362 lines, the one actually deployed). Old version. | Safe to delete — verify no env uses it |

---

## Swallowed-Exception Import Verification Table

Every `except...: pass` around an import or registration in production-reachable code, tested by actual import:

| Location | Module/Symbol | Exception Type | Import Result | Risk |
|----------|--------------|----------------|---------------|------|
| `content_qa_runner.py:760` | `practical_facts_gate.extract_practical_claims` | `except ImportError: pass` + `except Exception: pass` | **IMPORTS-OK** | Silent degradation if module breaks |
| `generate_tour_text.py:6449` | `directions_generator.generate_walking_directions` | `except (ImportError, Exception): pass` | **IMPORTS-OK** | Silent degradation if module breaks |
| `generate_tour_text_service.py:168` | `generate_tour_text._LAST_CLEAN_FAIL_EVIDENCE` | `except (ImportError, AttributeError): pass` | **IMPORTS-OK** | Lost debugging evidence |
| `generate_tour_text_service.py:281` | `generate_tour_text._LAST_VERIFICATION_TIER` | `except (ImportError, AttributeError): pass` | **IMPORTS-OK** | Lost tier metadata |
| `generate_tour_text_service.py:384` | `generate_tour_text._LAST_POI_LIST` | `except (ImportError, AttributeError): pass` | **IMPORTS-OK** | Lost verified flags |
| `tour_generation_modernized.py:40` | `urllib.parse` (+ network call) | bare `except: pass` | **IMPORTS-OK** (network fails locally, expected) | Silent auth failure on Cloud Run |
| `translation-service/translation_service.py:252` | `io` + `zipfile` (stdlib) | `except Exception: pass` | **IMPORTS-OK** | Corrupt ZIP silently passes |
| `spotify_processor.py:253` | `browser_automation._browser` | bare `except: pass` | **IMPORTS-FAIL** (no selenium) | Irrelevant — `spotify_processor` not reachable from any running service |
| `content_qa_runner.py:611` | `json` (stdlib) + file I/O | `except Exception: pass` | **IMPORTS-OK** | Benign — fallback to no-elements-file path is correct |
| `tour_orchestrator_service.py:119` | `swipe_preference_service.register_preference_routes` | `except ImportError` → **logs at ERROR** | **IMPORTS-OK** | Not silent — properly logged |
| `generate_tour_text_service.py:206` | `cost_meter.record_operation` | `except Exception` → **prints error** | **IMPORTS-OK** | Not silent — printed; cost ceiling is separate fail-closed block |

---

## Commands Used

```bash
# Carrier 1: Module nobody imports
grep -rn "from <module_name>\|import <module_name>" *.py */*.py 2>/dev/null | grep -v test | grep -v __pycache__

# Carrier 2: Function imported but never called
# Traced from entry points through import chains manually

# Carrier 3: Swallowed exceptions — discovery
find . -name "*.py" -not -path "./.git/*" -not -path "./audio_tour_app/*" -exec grep -l "except" {} \;
# Then for each file, extracted try/except/pass blocks near imports/registrations

# Carrier 3: Swallowed exceptions — verification
python3 -c "import sys; sys.path.insert(0, '.'); from <module> import <symbol>; print('OK')"

# Carrier 4: Blueprint/handler defined but never registered
grep -rn "Blueprint(" *.py
grep -rn "register_blueprint\|register.*routes" *.py */*.py

# Entry point verification
grep -E "container_name:" docker-compose-master.yml
grep -i "<service>" docker-compose-master.yml  # for each candidate
grep -i "<service>" docker-compose.yml          # check old compose

# Mobile app references
grep -rn "5022\|tourEditing\|tour_editing" audio_tour_app/lib/
```

---

## Limitations and False-Negative Risk

1. **Cloud Run paths not audited:** `tour_worker_service.py` and `Dockerfile.cloudrun` define Cloud Run deployments. Code reachable only through Cloud Run is invisible to this docker-compose-rooted analysis.

2. **Dynamic dispatch:** If any service uses `importlib.import_module()` or `getattr()` to load modules by string name, this audit will miss those paths. No such pattern was observed, but I did not exhaustively verify.

3. **Import verification ran on host, not in containers:** Imports were tested with the host Python (3.9) and host `sys.path`. A module that imports fine on the host may fail in a container (different Python version, missing package, different working directory). The `browser_automation` failure (no selenium) demonstrates this — selenium is installed in the newsletter-processor container image but not on the host. For the production services in master compose, the relevant packages are installed in their respective containers. I cannot verify inside them without Docker builds.

4. **Flutter/Dart code not audited** beyond confirming it calls non-existent backends (tour-editing at port 5022).

5. **Inter-service HTTP calls:** If Service A calls Service B at a URL that doesn't resolve (because B isn't running), that call path is effectively dead. Found tour-editing (Rank 1) and newsletter-processor (Rank 3) this way. May have missed others where the URL is constructed dynamically.

6. **"Works today" claims are point-in-time:** The import tests confirm the modules load successfully right now. They do not confirm the code *executes correctly* — only that the import path is not broken. A function that imports fine but throws at runtime would not be caught by this method.
