##### READY FOR REVIEW

# LOCAL-86: Download endpoint throws a Flask argument error

## Commit

```
d9590d8  LOCAL-86: Version-tolerant send_file wrapper — fixes download_name crash on Flask <2.0
```

Branch: `kiro/local86-send-file-flask`  
`git rev-list --count storied..HEAD` = 1

---

## Root cause

`generate_tour_text_service.py` calls:

```python
return send_file(output_path, as_attachment=True, download_name=job["output_file"])
```

But the service runs in a container built from `Dockerfile.generator` which installs
`requirements_generator.txt` → **Flask 1.1.4**. The `download_name` parameter was
introduced in Flask 2.0; Flask 1.1.4 only accepts `attachment_filename`.

---

## send_file call site inventory

| File | Container | Flask version | Signature used | Status before fix |
|------|-----------|---------------|----------------|-------------------|
| `generate_tour_text_service.py` | audioura-tour-generator-1 | 1.1.4 | `download_name=` | ❌ CRASH |
| `tour_orchestrator_service.py` | audioura-tour-orchestrator-1 | 1.1.4 | `attachment_filename=` | ✅ |
| `tour_generation_service.py` | audioura-tour-processor-1 | 2.3.3 | `download_name=` | ✅ |
| `map_delivery_service.py` | (docker-compose.yml root) | 2.0.1 | `download_name=` | ✅ |
| `map_delivery/app.py` | audioura-map-delivery-1 | 2.0.1 | Streaming Response | ✅ (no send_file) |
| `news_orchestrator_service.py` | news-orchestrator-1 | 2.3.3 | `download_name=` | ✅ |
| `polly_tts_service.py` | audioura-polly-tts-1-1 | 3.1.3 | `download_name=` | ✅ |
| `tour_delivery_service.py` | (not deployed) | unknown | `download_name=` | ⚠️ would crash on <2.0 |

---

## Fix approach

A `_compat_send_file()` wrapper is injected into each service file. At call time it
inspects `flask.send_file`'s signature and maps `download_name` ↔
`attachment_filename` to whichever the installed Flask supports:

```python
def _compat_send_file(path_or_file, **kwargs):
    sig = inspect.signature(_send_file)
    params = sig.parameters
    download_name = kwargs.pop("download_name", None)
    attachment_filename = kwargs.pop("attachment_filename", None)
    name = download_name or attachment_filename
    if name:
        if "download_name" in params:
            kwargs["download_name"] = name
        else:
            kwargs["attachment_filename"] = name
    return _send_file(path_or_file, **kwargs)

send_file = _compat_send_file
```

No Flask version pin changed. No requirements file altered. The same code works on
Flask 1.1.4, 2.x, and 3.x.

---

## Per-file changes

| File | Change |
|------|--------|
| `generate_tour_text_service.py` | +wrapper (fixes the crash) |
| `tour_orchestrator_service.py` | +wrapper (defensive, already worked) |
| `tour_generation_service.py` | +wrapper (defensive, already worked) |
| `map_delivery_service.py` | +wrapper (defensive, already worked) |
| `news_orchestrator_service.py` | +wrapper (defensive, already worked) |
| `polly_tts_service.py` | +wrapper (defensive, already worked) |
| `tour_delivery_service.py` | +wrapper (defensive, not currently deployed) |

---

## Evidence

### map_delivery /download-tour/29 — BEFORE fix

```
HTTP 200 size=7408370
```

### map_delivery /download-tour/29 — AFTER fix

```
HTTP 200 size=7408370
```

### tour_orchestrator /download/29 — AFTER fix

```
HTTP 200 size=7408370
ZIP validity: No errors detected in compressed data of /tmp/final_orch.zip.
```

### tour-generator compat wrapper proof (Flask 1.1.4 + download_name=)

```
Flask 1.1.4: download_name=False, attachment_filename=True
Wrapper result: 200, CD=attachment; filename=tour_test.zip
```

This proves `send_file(..., download_name='tour_test.zip')` no longer throws
`got an unexpected keyword argument 'download_name'` — the wrapper translates it
to `attachment_filename` which Flask 1.1.4 accepts.

### check_image_freshness (post-rebuild)

```
✅ audioura-tour-generator-1                FRESH
   Image: audioura-tour-generator:local86
✅ audioura-tour-orchestrator-1             FRESH
   Image: local-86-tour-orchestrator:latest
```

### All services healthy

```
Tour generator:     HTTP 200 /health
Tour orchestrator:  HTTP 200 (serves downloads)
News orchestrator:  HTTP 200 /health
Polly TTS:          HTTP 200 /health
Map delivery:       HTTP 200 /download-tour/29
```

---

## Database

No database operations performed. No rows touched.

---

## Regression

Diff against `~/audioura-worktrees/prepush-baseline` confirms changes are strictly
additive (the compat wrapper insertion) — no existing logic altered. All services
start, serve health checks, and deliver files at the same byte counts as before.

---

## Limitations

1. The `modified_generate_tour_text_service.py` and `modified_tour_orchestrator_service.py`
   files (historical/alternate versions in the repo root) also use `download_name` and
   are copied into the tour-generator container (`COPY *.py /app/`). They are NOT
   entrypoints and are never executed, so they won't crash — but they lack the wrapper.
   A future task could clean these up or add the wrapper there too.

2. The `tour_editing_phase2*.py` files (ports 5020/5022) also use `download_name` with
   `send_file`. These services are not in `docker-compose-master.yml` (only in the root
   `docker-compose.yml`). They are not running. If revived, they'd need the wrapper.

3. `map_delivery/app.py` (the actual deployed map-delivery) uses a streaming `Response()`
   instead of `send_file`, so it's immune to this bug. The root `map_delivery_service.py`
   (used only by the root `docker-compose.yml`, not docker-compose-master.yml) was still
   patched defensively.

4. `polly_tts_service.py`'s Dockerfile does bare `pip install flask` (no pin).
   On Python 3.9-slim today that resolves to Flask 3.1.3 which has `download_name`.
   The wrapper ensures it continues working even if the base image changes to something
   where Flask gets constrained to <2.0 (unlikely but possible).
