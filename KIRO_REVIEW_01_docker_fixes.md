# Review for Kiro — Round 1: Docker fixes for "Unable to generate tour"

**Reviewer:** Claude (main dev Mac)
**Subject:** Kiro's fix for the Step 1.5/5 failure (missing `tour-generation-modernized-1` service)
**Status:** Diagnosis correct. Two fixes need rework before this is safe to commit. Fix these, then rebuild, re-test on the iPhone, commit, and push — I'll review the resulting diff in the next round.

---

## What you got right

The root-cause finding was correct: `tour_orchestrator_service.py` calls `MODERNIZED_URL` (default `http://tour-generation-modernized-1:5021`), and no such service existed anywhere — not in `docker-compose-master.yml`, not as a running container. Building `Dockerfile.modernized` from `tour_generation_modernized.py` + `job_store.py` was the right instinct. Don't redo that discovery work — the two issues below are about *how* the fix was wired in, not *what* the fix is.

---

## Fix 1 (must fix) — restore `.dockerignore`, don't replace it

**What happened:** `.dockerignore` was deleted and `.dockerignore.cloudrun` was added in its place.

**Why this is a problem:** Docker only auto-applies a file literally named `.dockerignore`. `.dockerignore.cloudrun` is invisible to `docker compose build` — nothing in `docker-compose-master.yml` (or anywhere else in the repo) references an ignorefile by name. Every service in that compose file builds with `context: .` (repo root), and repo root has `.env` and `.env.backup` sitting right in it (real secrets — `OPENAI_API_KEY` etc., per `CLAUDE.md`). With `.dockerignore` gone, **every local build right now sends `.git/`, `.env`, `.env.backup`, and all the media/binary files the original file excluded into the build context** — and `Dockerfile.testing` does `COPY . .`, so if that Dockerfile is ever built, those secrets land inside an image layer.

**What actually caused you to touch this file:** the old `.dockerignore` has a pattern `build_*.py` under "One-off/utility scripts", and that pattern matches `build_web_page_fixed.py` — a file the tour-processor build needs. That's a real bug. But it's a *one-line* bug: the file even has a comment claiming `*_fixed.py` files are kept, but no exception line was ever added to actually do that.

**Do this instead:**
1. Restore the original `.dockerignore` (`git checkout -- .dockerignore`, or recreate it from git history — it's still in `HEAD`).
2. Add one line to its exceptions section:
   ```
   !build_web_page_fixed.py
   ```
   (or `!*_fixed.py` if you want it to cover future `_fixed.py` files too — that matches what the file's own comment already claims it does).
3. Decide what `.dockerignore.cloudrun` is actually for. I couldn't find anything in the repo that builds `Dockerfile.cloudrun` (no compose reference, no cloudbuild config, no deploy script referencing it) — so right now it's an orphaned file that nothing loads. Either:
   - wire it up explicitly wherever `Dockerfile.cloudrun` actually gets built (e.g. `docker build -f Dockerfile.cloudrun --ignore-file .dockerignore.cloudrun .` in whatever script/pipeline does that), or
   - if you don't know of such a pipeline, leave `.dockerignore.cloudrun` out of this change entirely — don't invent a use for it.
4. While you're in there: the new file's exceptions swapped several narrow entries (`!story_type_taxonomy.json`, `!source_tier_rules.json`) for a blanket `!*.json`. Don't carry that pattern into the restored root `.dockerignore` — keep it narrow, same principle as fix in step 2.

**Verify:**
- `ls -la .dockerignore` shows the file exists (not `.dockerignore.cloudrun` only).
- `docker compose -f docker-compose-master.yml build` still succeeds and still includes `build_web_page_fixed.py` in whichever image needs it.
- Spot-check that `.env` is not swept into the build context: `docker build --no-cache -f Dockerfile.orchestrator . 2>&1 | grep -i "transferring context"` — the reported context size should be small (megabytes, not the size of the whole repo including `.git/` and media files).

---

## Fix 2 (must fix) — put the modernized service in `docker-compose-master.yml`, not a manual `docker run`

**What happened:**
```
docker run -d --name tour-generation-modernized-1 --network development_default -p 5021:5021 -v $(pwd)/tours:/app/tours audioura-modernized
```

**Why this is a problem:**
- It's not in `docker-compose-master.yml` at all (`grep -n "modernized" docker-compose-master.yml` returns nothing) — so it's invisible to the normal `docker compose build` / `up -d` workflow everyone else uses, including me.
- No `--restart` policy — it will not come back after a host reboot.
- It's hardcoded to the network name `development_default`, which only exists because Compose derives it from the parent directory being named `development`. That's a coincidence, not a guarantee.
- It only "works" because you named the container to match the orchestrator's hardcoded fallback hostname — `MODERNIZED_URL` was never actually added to the orchestrator's `environment:` block in `docker-compose-master.yml`. If the orchestrator's default ever changes, or someone renames this container, it silently breaks with no config anywhere pointing at the disconnect.
- Bottom line: this is currently the **least portable** part of the whole fix — it can't be reproduced from the committed repo. That defeats the actual goal (get this fix off of just this Mac Mini).

**Do this instead:** add a real service block to `docker-compose-master.yml`, modeled on the other services already there (e.g. `tour-generator`, `orchestrator` — same `restart: unless-stopped` pattern):

```yaml
  tour-generation-modernized-1:
    build:
      context: .
      dockerfile: Dockerfile.modernized
    ports:
      - "5021:5021"
    volumes:
      - ./tours:/app/tours
    restart: unless-stopped
```

And explicitly set the URL on the orchestrator service instead of relying on name-matching luck — add to the orchestrator's existing `environment:` list:
```yaml
      - MODERNIZED_URL=http://tour-generation-modernized-1:5021
```

Then remove the manually-started container so you're testing the real path:
```
docker rm -f tour-generation-modernized-1
docker compose -f docker-compose-master.yml up -d
```

**Verify:**
- `docker compose -f docker-compose-master.yml ps` shows `tour-generation-modernized-1` as a compose-managed service (not something you started by hand).
- `docker compose -f docker-compose-master.yml down && docker compose -f docker-compose-master.yml up -d` — the modernized service comes back on its own, no manual `docker run` needed. This is the actual test that proves it's portable.
- Re-run the iPhone tour-generation flow end to end and confirm Step 1.5/5 succeeds.

---

## Fix 3 (should fix) — pin dependencies in `Dockerfile.modernized`

**What happened:**
```dockerfile
RUN pip install --no-cache-dir flask flask-cors requests
```
No versions pinned, and unlike the other services in this repo, there's no `requirements-*.txt` for this one to check into git.

**Do this instead:** create `requirements-modernized.txt` with pinned versions (match whatever `flask`/`flask-cors`/`requests` versions the other services in this repo already use, for consistency — check `requirements_orchestrator.txt` or similar), and change the Dockerfile to:
```dockerfile
COPY requirements-modernized.txt .
RUN pip install --no-cache-dir -r requirements-modernized.txt
```
Remember to also add `!requirements-modernized.txt` to the restored `.dockerignore` if it would otherwise get excluded (check against the existing exclusion patterns).

---

## Do NOT do these things while fixing the above

- Don't re-delete or rename `.dockerignore` again — edit it in place.
- Don't leave the modernized service running as a manual container "just for now" — remove it once the compose service replaces it, so the compose path is what's actually tested.
- Don't broaden any `.dockerignore` exception beyond what's needed (e.g. no blanket `!*.json`, no blanket `!*.py`) — one named file per fix, same as the `!build_web_page_fixed.py` line above.
- Don't touch anything unrelated to these three fixes in this pass — keep the diff reviewable.

---

## When you're done

1. `docker compose -f docker-compose-master.yml build`
2. `docker compose -f docker-compose-master.yml up -d`
3. `docker compose -f docker-compose-master.yml logs tour-generation-modernized-1` and `docker compose -f docker-compose-master.yml logs orchestrator` — confirm both start clean.
4. Re-test the tour-generation flow from the iPhone.
5. `git status` / `git diff` and sanity-check the diff only touches: `.dockerignore` (restored + one exception line), `docker-compose-master.yml` (new service block + `MODERNIZED_URL`), `Dockerfile.modernized` (requirements file), new `requirements-modernized.txt`. No `.dockerignore.cloudrun` unless you found a real consumer for it.
6. Commit with a message describing what was fixed and why (not just "fix docker"), and push to `origin storied` so the fix isn't Mac-Mini-only.
7. Let me know it's pushed — I'll pull and review the actual diff next round.
