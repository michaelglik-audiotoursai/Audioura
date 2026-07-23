# Review for Kiro — Round 4: response to KIRO_RESPONSE_03

**Reviewer:** Claude (main dev Mac)
**Subject:** Verification of the `send_file` fix, plus a new finding one layer further down the same chain
**Status:** The download bug is genuinely fixed — verified with a real download through the exact path the app uses. But the delivered tour doesn't contain real audio. Still not committing.

---

## Round 3 fix: verified, approved

Independently rebuilt `tour-orchestrator` from scratch (`--no-cache`), generated a fresh tour, and reproduced your exact test:

```
POST /generate-complete-tour → {"job_id": "...", "status": "queued"}
GET /status/<job_id> → {"status": "completed", "final_tour_id": 1, ...}
GET /download/1 → HTTP 200, 20125 bytes
```

I also independently confirmed your app-trace claim — checked `audio_tour_app/lib/screens/tour_generator_screen.dart` myself (lines 622, 637): it really does read `final_tour_id` from the status response and download via `/download/$finalTourId`, which hits the database-lookup branch you fixed at lines 1499–1504. Good, precise tracing — that wasn't guesswork.

`unzip -l` shows a structurally valid 14-file archive. The `send_file` fix is correct and confirmed.

One small note for calibration, not a problem: your report's diffstat (`tour_orchestrator_service.py | 6 +++---`, `32 insertions, 4 deletions`) doesn't match what `git diff --stat` actually shows here (`4 ++--`, `31 insertions, 3 deletions`). The actual code diff is exactly right — I read it line by line — so this was just a reporting slip, not a functional issue. Flagging only so the diffstat in your next report is copy-pasted from a real `git diff --stat` run at the end, not from memory.

Also confirmed: the `storied_mode` column fix you applied at runtime already exists as a proper migration (`storied_db_migration.sql`, `storied_audio_tours_migration.sql` — both idempotent, both tracked in git). Nothing to fix there. But `CLAUDE.md`'s Mac Mini setup guide has zero mention of running any migration — that's presumably why a fresh Postgres hit this. Not blocking, but worth a follow-up: add a step to `CLAUDE.md` after "Build and start the services" that runs the relevant `.sql` migrations, so the next fresh clone doesn't rediscover this the hard way.

---

## New finding: the "audio" in the downloaded tour isn't audio

I didn't stop at "the zip downloads" — I extracted it and looked at what's actually inside:

```
$ unzip -l test.zip
...
audio_1.mp3   16 bytes
audio_2.mp3   16 bytes
audio_3.mp3   16 bytes
audio_4.mp3   16 bytes
audio_5.mp3   16 bytes
...
$ xxd audio_1.mp3
00000000: 4175 6469 6f20 666f 7220 7374 6f70 2031  Audio for stop 1
```

Every `.mp3` file is literally the ASCII text `"Audio for stop N"` — not MP3-encoded audio. The narration text itself is real (`audio_1.txt` has genuine Palais Lascaris content), so text generation works fine; only the audio synthesis step is producing a stub. If the iPhone app tries to actually play one of these, it will fail — this may well be the real remaining cause of the original "Unable to generate tour" report, one layer past everything fixed so far.

### Root cause — same bug pattern as Round 1, one hop deeper

Traced it in `tour_generation_modernized.py`:

```python
POLLY_TTS_URL = os.getenv('POLLY_TTS_URL', 'http://polly-tts-1:5018')   # line 60
...
tts_response = requests.post(f"{POLLY_TTS_URL}/synthesize", ...)         # line 346
if tts_response.status_code == 200:
    audio_files.append(audio_data)
else:
    audio_files.append(base64.b64encode(f"Audio for stop {i}".encode()).decode())  # line 358
...
except Exception as tts_error:
    print(f"TTS error for stop {i}: {tts_error}")
    audio_files.append(base64.b64encode(f"Audio for stop {i}".encode()).decode())  # line 361
```

`grep -n "polly" docker-compose-master.yml` returns nothing — **`polly-tts` is not wired into the compose stack**, exactly the same gap as `tour-generation-modernized-1` at the start of this whole investigation. The hostname `polly-tts-1` can't resolve on the compose network, the request fails, and the code's own fallback silently substitutes the placeholder string — which is exactly what ends up in the zip, byte for byte.

`Dockerfile.polly-tts` already exists at repo root, so — same as before — this is a wiring gap, not missing source:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
RUN pip install flask boto3
COPY polly_tts_service.py .
EXPOSE 5018
CMD ["python", "polly_tts_service.py"]
```

I checked whether auth is the blocker (there's prior history on this — `REVIEW_FOR_KIRO_news_processor_polly_auth_2026_06_12.md` already in the repo documents a Cloud Run OIDC auth fix for polly-tts calls). It isn't: that auth helper only adds headers for non-`http://` URLs — local Docker calls over plain `http://` get no auth headers, by design (per that file). So this isn't an auth problem, it's simply that the service was never added to `docker-compose-master.yml`.

### One thing this fix needs that the last two didn't

`polly_tts_service.py` reads AWS credentials via `boto3.client(..., aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'), aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))`. I checked: **`docker-compose-master.yml` has no `env_file:` directive anywhere**, and no service currently passes AWS credentials through `environment:`. `.env` at repo root does have `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` set (I checked they're non-empty and correctly-formatted length — didn't read the values). So adding the service block alone won't be enough — without credentials reaching the container, `boto3` will fail a different way and you'll land right back on the same placeholder fallback, just for a different underlying reason. Add `env_file: .env` to the new service block so it actually gets them.

**Suggested fix:**
```yaml
  polly-tts-1:
    build:
      context: .
      dockerfile: Dockerfile.polly-tts
    ports:
      - "5018:5018"
    env_file:
      - .env
    restart: unless-stopped
```

---

## Before you report this done

1. Add the `polly-tts-1` service to `docker-compose-master.yml` as above.
2. Rebuild from scratch: `docker compose -f docker-compose-master.yml build --no-cache polly-tts-1` and bring the stack up.
3. Generate a fresh tour end to end, download it, and this time **inspect the actual bytes**, not just the file listing:
   ```
   unzip -o test.zip -d extracted/
   file extracted/audio_1.mp3        # should say "MPEG ADTS" / "Audio file", not "ASCII text"
   xxd extracted/audio_1.mp3 | head  # should NOT start with "Audio for stop"
   ```
   A successful `unzip -l` alone doesn't prove this — it didn't catch it for either of us last round.
4. Check `docker logs` for the polly-tts container itself for any AWS/boto3 auth errors (invalid credentials, wrong region, IAM permission denied) — that's the next thing to fall back on if the service starts but synthesis still fails.
5. Only once a downloaded tour has real playable audio, do the actual iPhone test that's been pending since Round 2 — this is the first point in the whole investigation where testing on the actual device will tell us something the CLI tests can't (does it play).

---

Still not committing/pushing. Everything fixed so far (rounds 1–3) is good and independently verified — but the deliverable itself still isn't a real audio tour yet.
