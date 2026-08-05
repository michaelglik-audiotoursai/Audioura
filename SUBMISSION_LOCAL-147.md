##### READY FOR REVIEW

## LOCAL-147 — Newsletter Processor: Option A (No Compose Entry)

### Commit

```
git log --oneline storied..HEAD
```

### Summary

Round 3 resolution: **Option A — do not add `newsletter-processor` to
`docker-compose-master.yml`.**

The service's credential gate (added in round 2) lives in the source file,
but the image (`audioura-tour-generator:latest`) contains the **ungated**
version with plaintext credential storage. The builder is hung, so no new
image can be built. A `docker compose up -d` with no arguments would run
the image's copy — which has no gate — exposing `/submit_credentials` and
`/key_exchange` with plaintext storage, exactly the round-2 scenario.

**Why Option A over B or C:**

- **Option B** (volume mount) works but introduces import fragility: if the
  mounted source references modules not in the image, the service crashes
  at startup. Verified it works today but is fragile across updates.
- **Option C** (no port publish) still runs the ungated code inside the
  network — weaker containment.
- **Option A** is simplest and correct: the service does nothing for anyone
  (`/newsletters_v2` returns empty; no sources registered). No cost to
  leaving it out until the image is rebuilt with the gate baked in. The
  compose entry can be added in one line the day the builder is fixed.

The source gate is retained so it will be baked into the next image build.

### Per-File Changes

| File | Lines | What |
|------|-------|------|
| `docker-compose-master.yml` | -26 | Remove `newsletter-processor` service entry (cannot deploy ungated image) |
| `newsletter_processor_service.py` | (unchanged this commit; +17 from round 2) | Gate retained in source for next image build |
| `SUBMISSION_LOCAL-147.md` | rewritten | Updated for round 3 |

### Verbatim Evidence

**No compose file can start the service:**
```
$ grep -c "newsletter-processor" docker-compose-master.yml
0
```

**The source gate is in place (ready for next image build):**
```
$ grep -c "CREDENTIAL_ENDPOINTS_ENABLED" newsletter_processor_service.py
3
```

**Proof the gate works in the deployed context (volume-mounted source):**

Container started with `newsletter_processor_service.py` mounted read-only:
```
$ docker exec newsletter-processor-test-147 grep -c "CREDENTIAL_ENDPOINTS_ENABLED" /app/newsletter_processor_service.py
3
```

Health works:
```
$ curl -s http://localhost:5017/health
{"service":"newsletter_processor","status":"healthy"}
HTTP 200
```

Credential endpoints refuse (503):
```
$ curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:5017/key_exchange -H "Content-Type: application/json" -d '{}'
{"message":"Credential endpoints are disabled. At-rest encryption is not configured.","status":"error"}
HTTP 503

$ curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:5017/submit_credentials -H "Content-Type: application/json" -d '{}'
{"message":"Credential endpoints are disabled. At-rest encryption is not configured.","status":"error"}
HTTP 503
```

Newsletter processing unaffected:
```
$ curl -s http://localhost:5017/newsletters_v2
{"newsletters":[],"status":"success"}
HTTP 200
```

**Container stopped, removed, and gone:**
```
$ docker stop newsletter-processor-test-147 && docker rm newsletter-processor-test-147
newsletter-processor-test-147
newsletter-processor-test-147

$ docker ps --format "{{.Names}}" | grep newsletter-processor
(no output — container is gone)
```

**Existing containers untouched:**
```
$ diff /tmp/containers_before_147r3.txt /tmp/containers_after_147r3.txt
(no output — identical, 21 containers unchanged)
```

### Row Counts

| Table | Before | After |
|-------|--------|-------|
| `audio_tours` | 106 | 106 |
| `stop_metrics` | 1011 | 1011 |
| `user_subscription_credentials` | 0 | 0 |

### Rollback

```bash
# To restore the compose entry (only safe after image is rebuilt with gate):
git revert <this-commit> --no-edit
```

No runtime rollback needed — no container is running.

### Limitations

1. **Service is not deployed.** Newsletter processing (browser-based article
   extraction, Spotify/Apple Podcasts, `content_expander.py`) remains
   unreachable until the image is rebuilt with the gated source. This is
   acceptable because `/newsletters_v2` returns empty — no sources are
   registered, so the service was doing nothing for anyone.

2. **Builder hung.** The compose entry cannot be re-added until a fresh
   image is built containing the gate. The source change (round 2) ensures
   the gate will be present in the next build automatically.

3. **One-line restoration.** When the builder is fixed and the image is
   rebuilt, adding the service back requires only re-inserting the compose
   entry (available in git history, commit bc0f395).
