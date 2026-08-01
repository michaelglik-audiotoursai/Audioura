##### READY FOR REVIEW

## LOCAL-89: Fix freshness checker false positives on every service except tour-generator

**Commit:** `b41144d` on branch `kiro/local89-freshness-false-positive`  
**Date:** 2026-08-01T00:15:xx-04:00  
**Author:** Mac Mini Kiro

---

### Per-file changes

| File | Lines | Change |
|------|-------|--------|
| `check_image_freshness.py` | +225/-182 (rewrite) | Three-state logic (FRESH/STALE/UNKNOWN); host-dir resolution per service; file-rename mapping |
| `docker-compose-master.yml` | +57/-19 | GIT_SHA build arg for all 19 services; subdirectory services converted to full build form |
| `Dockerfile.orchestrator` | +7/-1 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.modernized` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.polly-tts` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.tour-processor` | +6/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.treats` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.tour-id-resolution` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.news-generator` | +6/-1 | Added entitlements.py + build_manifest.py COPY + manifest generation |
| `Dockerfile.news-processor` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.news-orchestrator` | +6/-1 | Added entitlements.py + build_manifest.py COPY + manifest generation |
| `Dockerfile.newsletter-link-extractor` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.background-article-processor` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `Dockerfile.simple-news-search` | +5/-0 | Added build_manifest.py COPY + manifest generation step |
| `map_delivery/Dockerfile` | +5/-0 | Added manifest generation step (COPY . . already brings it in) |
| `user-tracking/Dockerfile` | +5/-0 | Added manifest generation step |
| `tour-update-service/Dockerfile` | +5/-0 | Added manifest generation step |
| `coordinates_fromAI/Dockerfile` | +4/-0 | Added explicit COPY build_manifest.py + manifest generation |
| `voice_control/Dockerfile` | +5/-0 | Added manifest generation step |
| `translation-service/Dockerfile` | +5/-1 | Added build_manifest.py to COPY + manifest generation step |
| `map_delivery/build_manifest.py` | +72 (new) | Copy of root build_manifest.py for isolated build context |
| `user-tracking/build_manifest.py` | +72 (new) | Copy of root build_manifest.py for isolated build context |
| `tour-update-service/build_manifest.py` | +72 (new) | Copy of root build_manifest.py for isolated build context |
| `coordinates_fromAI/build_manifest.py` | +72 (new) | Copy of root build_manifest.py for isolated build context |
| `voice_control/build_manifest.py` | +72 (new) | Copy of root build_manifest.py for isolated build context |
| `translation-service/build_manifest.py` | +72 (new) | Copy of root build_manifest.py for isolated build context |

---

### Root cause of the false positives

Two bugs in the original `check_image_freshness.py`:

1. **Wrong host directory.** Services with subdirectory build contexts (map-delivery, user-api-2, tour-update, coordinates-fromai, voice-control, translation-service) had their container files compared against the repo root. E.g., map-delivery's container file `app.py` (md5 `a603450c`) was compared against `./app.py` (md5 `97c9fbf8`) instead of `./map_delivery/app.py` (md5 `a603450c`). Identical files reported as drifted.

2. **File renames not tracked.** `Dockerfile.treats` does `COPY treats_service.py app.py` and `Dockerfile.tour-processor` does `COPY build_mp3_simple.py ./build_mp3.py`. The checker compared container `app.py` against host `app.py` (wrong file) instead of host `treats_service.py`.

---

### Acceptance criteria — evidence

#### 1. Three-state output (FRESH/STALE/UNKNOWN) — no healthy service reports red

```
$ python3 check_image_freshness.py
================================================================================
IMAGE FRESHNESS CHECK — 2026-08-01T00:14:48.277508
================================================================================

✅ audioura-map-delivery-1                  FRESH (no manifest — compared live)
✅ audioura-tour-id-resolution-1            FRESH (no manifest — compared live)
✅ audioura-translation-service-1           FRESH (no manifest — compared live)
✅ audioura-treats-1                        FRESH (no manifest — compared live)
✅ audioura-user-api-2-1                    FRESH (no manifest — compared live)
✅ news-processor-1                         FRESH (no manifest — compared live)
✅ audioura-tour-update-1                   FRESH (no manifest — compared live)
✅ news-generator-1                         FRESH (no manifest — compared live)
✅ simple-news-search-1                     FRESH (no manifest — compared live)
✅ audioura-tour-processor-1                FRESH (no manifest — compared live)
✅ audioura-tour-generation-modernized-1-1  FRESH (no manifest — compared live)
✅ audioura-coordinates-fromai-1            FRESH (no manifest — compared live)
✅ newsletter-link-extractor-1              FRESH (no manifest — compared live)
✅ audioura-polly-tts-1-1                   FRESH (no manifest — compared live)
✅ audioura-voice-control-1                 FRESH (no manifest — compared live)
❌ audioura-tour-generator-1                STALE (genuine — 8 drifted files, local86 tag)
❌ audioura-tour-orchestrator-1             STALE (genuine — local-86 private image)
❌ news-orchestrator-1                      STALE (genuine — old cost_meter.py)
⚠️ development-postgres-2-1                 UNKNOWN (no Python files — expected)

Summary: ✅ 15 FRESH | ❌ 3 STALE | ⚠️  1 UNKNOWN
```

All 15 healthy services report FRESH. The 3 STALE are genuinely stale
(running private images from LOCAL-86 work or have actual code drift).
Postgres correctly reports UNKNOWN (not red).

#### 2. Deliberate drift detection on non-generator service

**STALE after host edit:**
```
$ echo "# drift test" >> map_delivery/app.py
$ python3 check_image_freshness.py --verbose --container local-89-map-delivery-test

❌ local-89-map-delivery-test               STALE
   SHA: 71140e8d7fec44a740bb8f2e4d83f30a4c10f417
   Built: 2026-08-01T04:13:56.281090+00:00
   Files checked: 2, drifted: 1
      ⚠ app.py: host=332de860… container=a603450c… (host size: 12652)
```

**FRESH after rebuild:**
```
$ docker build -t local-89-map-delivery:latest --build-arg GIT_SHA=$(git rev-parse HEAD) ./map_delivery
$ docker run -d --name local-89-map-delivery-test ... local-89-map-delivery:latest
$ python3 check_image_freshness.py --verbose --container local-89-map-delivery-test

✅ local-89-map-delivery-test               FRESH
   SHA: 71140e8d7fec44a740bb8f2e4d83f30a4c10f417
   Built: 2026-08-01T04:14:17.274810+00:00
   Files checked: 2, drifted: 0
   Verified: app.py, build_manifest.py
```

#### 3. `code_sha` is a real commit hash

```
$ docker run --rm local-89-map-delivery:latest cat /app/.build_manifest.json
{
  "git_sha": "71140e8d7fec44a740bb8f2e4d83f30a4c10f417",
  "build_time": "2026-08-01T04:13:56.281090+00:00",
  "files": {
    "app.py": {"md5": "a603450c99ffa19b7e20c377e4c57830", "size": 12639},
    "build_manifest.py": {"md5": "25088b66eb64f635da7e64a49431e109", "size": 2188}
  }
}
```

`71140e8` matches `git rev-parse HEAD` on the branch at build time.

#### 4. map-delivery resolves — FRESH, not STALE

```
$ python3 check_image_freshness.py --verbose --container audioura-map-delivery-1

✅ audioura-map-delivery-1                  FRESH (no manifest — compared live)
   SHA: no_manifest
   Built: no_manifest
   Files checked: 1, drifted: 0
   Source dir: /Users/micha/audioura-worktrees/LOCAL-89/map_delivery
   Verified: app.py
```

Host `map_delivery/app.py` md5: `a603450c99ffa19b7e20c377e4c57830`
Container `/app/app.py` md5: `a603450c99ffa19b7e20c377e4c57830` ← identical

#### 5. tours-near endpoint intact

```
$ curl -s "http://localhost:5005/tours-near/43.7009358/7.2683912?radius=50" | python3 -c "
import json,sys; d=json.load(sys.stdin)
ids=sorted(t['id'] for t in d['tours'])
print(ids)
assert ids==[1,12,14,17,21,24,27,28,29]"

[1, 12, 14, 17, 21, 24, 27, 28, 29]
```

#### 6. No DB changes

```
$ psql -h localhost -p 5433 -U admin -d audiotours -t -c "SELECT COUNT(*) FROM audio_tours;"
55
```

Row count: 55 before, 55 after.

#### 7. No private images left running

The test container `local-89-map-delivery-test` was stopped and removed.
The `local-89-map-delivery:latest` image was deleted.
All compose-managed containers remain on their original images.

---

### Constraints compliance

- ⛔ No `DELETE FROM audio_tours` anywhere in this commit.
- ⛔ No service left running a private image — test containers cleaned up.
- ⛔ `audioura-tour-generator-1` not touched (constraint: never touch it).
- `.dockerignore` re-include `!build_manifest.py` already present from LOCAL-63.

---

### Limitations

1. **Existing containers don't have manifests yet.** Until services are rebuilt with this commit, they use the fallback (direct md5 comparison). The fallback works correctly — it just can't report `code_sha`.

2. **news-orchestrator will remain STALE** until it's rebuilt. The running container has `cost_meter.py` from an older version that genuinely differs from the host. The updated Dockerfile no longer copies `cost_meter.py` (it's not imported) — a rebuild will fix this.

3. **tour-generator and tour-orchestrator are genuinely STALE** — they're running LOCAL-86 private images (`audioura-tour-generator:local86`, `local-86-tour-orchestrator:latest`). A rebuild from compose will fix them, but that's outside this task's scope per the "never touch audioura-tour-generator-1" constraint.

4. **`build_manifest.py` is duplicated** in 6 subdirectories because each has an isolated build context. If the manifest logic changes, all copies need updating. Alternative was multi-stage builds or changing all build contexts to root, both more disruptive.
