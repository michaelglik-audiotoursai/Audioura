##### READY FOR REVIEW

# LOCAL-126: Healthcheck repair — false-unhealthy from missing `curl`

## Problem

Four containers report `(unhealthy)` because their healthcheck calls `curl`
which is not installed in the images. The services themselves are fine — the
signal is a false alarm teaching operators to ignore Docker health status.

## Per-container audit

| Container | Has healthcheck | Has `curl` | Probe fails now | Proposed probe | Verified via `docker exec` |
|---|---|---|---|---|---|
| `audioura-tour-generator-1` (c20c3ebf7a92) | ✅ | ❌ | ✅ failing | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"` | ✅ exit 0 |
| `audioura-tour-processor-1` (7b6bff2e4ddf) | ✅ | ❌ | ✅ failing | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')"` | ✅ exit 0 |
| `audioura-map-delivery-1` (fb3491c10c39) | ✅ | ❌ | ✅ failing | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:5005/health')"` | ✅ exit 0 |
| `audioura-voice-control-1` (cfc6797748f8) | ✅ | ❌ | ✅ failing | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:5008/health')"` | ✅ exit 0 |
| `audioura-coordinates-fromai-1` (91a678b57a05) | ✅ | ✅ (`/usr/bin/curl`) | ❌ passing (healthy) | No change needed — existing `curl` probe works | ✅ exit 0 |

## Probe choice rationale

**Python `urllib.request`** over alternatives:

1. **No rebuild required.** `curl` would need `apk add curl` in Dockerfiles →
   image rebuild → currently impossible (builder hangs, D32 documents this).
2. **Already present.** All four containers run Python (3.9.25 or 3.10.20).
   `urllib.request` is in the standard library — zero additional dependencies.
3. **Equivalent semantics.** Opens an HTTP connection, reads the response, raises
   on non-2xx status (which makes `docker exec` return non-zero → healthcheck
   fails). Same behavior as `curl -f`.
4. **`wget` not available either.** These are slim Python images without common
   Unix HTTP utilities. Python stdlib is the only guaranteed HTTP client.

Why NOT add `curl` to Dockerfiles:
- Requires a rebuild; builds are currently timing out (D32).
- Adds a package dependency for something the stdlib already provides.
- Rebuilds risk environment changes on images that have been running stably.

## Compose diff

```diff
-      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
+      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"]

-      test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
+      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')"]

-      test: ["CMD", "curl", "-f", "http://localhost:5005/health"]
+      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5005/health')"]

-      test: ["CMD", "curl", "-f", "http://localhost:5008/health"]
+      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5008/health')"]
```

`coordinates-fromai` left unchanged — already has `curl` and shows `(healthy)`.

## No-restart confirmation

**Container IDs, names, and uptimes are identical before and after.**

Before:
```
c20c3ebf7a92   audioura-tour-generator-1    Up 23 hours (unhealthy)
7b6bff2e4ddf   audioura-tour-processor-1    Up 32 hours (unhealthy)
fb3491c10c39   audioura-map-delivery-1      Up 30 hours (unhealthy)
cfc6797748f8   audioura-voice-control-1     Up 3 days (unhealthy)
91a678b57a05   audioura-coordinates-fromai-1 Up 30 hours (healthy)
```

After:
```
c20c3ebf7a92   audioura-tour-generator-1    Up 23 hours (unhealthy)
7b6bff2e4ddf   audioura-tour-processor-1    Up 32 hours (unhealthy)
fb3491c10c39   audioura-map-delivery-1      Up 31 hours (unhealthy)
cfc6797748f8   audioura-voice-control-1     Up 3 days (unhealthy)
91a678b57a05   audioura-coordinates-fromai-1 Up 30 hours (healthy)
```

No container was restarted, rebuilt, stopped, or removed. Uptimes continue
counting up (30→31h on map-delivery is wall-clock elapsed during this task).

## Constraint checks

- `audio_tours` row count: **88** (before and after)
- `tours-near/43.7009358/7.2683912?radius=50` returns: **[1, 12, 14, 17, 21, 24, 27, 28, 29]** ✓

## Applying the change

To make the healthchecks take effect, LEAD or Michael must run:

```bash
docker-compose -f docker-compose-master.yml up -d --no-build
```

This re-creates containers with the new healthcheck config using existing
images (no rebuild). The `--no-build` flag ensures no build is attempted.
**Wait until Michael returns or the builder is no longer hung** — `up -d`
without `--no-build` would attempt a build and hang.

Alternatively, apply per-container with `--no-deps`:
```bash
docker-compose -f docker-compose-master.yml up -d --no-build --no-deps tour-generator tour-processor map-delivery voice-control
```

After applying, within 30–90 seconds the containers will transition from
`(unhealthy)` to `(healthy)`.

## Files changed

| File | Change |
|---|---|
| `docker-compose-master.yml` | 4 healthcheck lines: `curl -f` → `python -c "import urllib.request; ..."` |
| `SUBMISSION_LOCAL-126.md` | This submission artifact (new file) |

## Limitations

- The change is **not applied** — containers still show `(unhealthy)` until
  someone runs `docker-compose up -d --no-build`.
- If a future image drops Python from `$PATH` or switches to a non-Python
  base, the probe would need updating. This is unlikely — these are Python
  service containers.
- `coordinates-fromai` retains its `curl` probe. If that image is ever
  rebuilt without `curl`, it would need the same treatment.
