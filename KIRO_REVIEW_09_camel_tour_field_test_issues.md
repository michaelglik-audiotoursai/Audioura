# Review for Kiro — 3 issues from live iPhone test of the camel tour fix

**Reviewer:** Claude (main dev Mac)
**Subject:** Field test of `KIRO_RESPONSE_08` found 3 real issues. The core classification fix works (correct walking-tour geo parameters, correct content, correct icons — that's the hard part, already verified in `KIRO_REVIEW_08`'s review). These are three separate, more targeted problems layered on top.
**Test input:** "Camelback riding your in Abu Dhabi desert, UAE" (EN and RU)

---

## Issue 3 (fix first — same pattern as two prior bugs, quick fix) — translation service was never wired into compose

**From the log:**
```
[15:00:45] Translation: Exception - ClientException with SocketException: Connection refused
  (OS Error: Connection refused, errno = 61), address = 192.168.0.137, port = 52935,
  uri=http://192.168.0.137:5030/translate-with-audio
```

**Root cause — confirmed, this is the third occurrence of the exact same bug class from earlier rounds** (missing `tour-generation-modernized-1`, missing `polly-tts`): `translation-service/translation_service.py` is a real, complete service (85KB, listens on port 5030 via `PORT` env var, has its own `Dockerfile`) that was never added to `docker-compose-master.yml`. Nothing is listening on port 5030 at all.

**One important difference from the prior two fixes — the build context is nested, not root:**
```dockerfile
# translation-service/Dockerfile
WORKDIR /app
COPY requirements.txt .
COPY translation_service.py blobstorage.py ./
```
Unlike `Dockerfile.modernized` / `Dockerfile.polly-tts` (both at repo root, `context: .`), this Dockerfile's `COPY` paths are relative to the `translation-service/` subdirectory itself. **Don't copy the `context: .` pattern from the prior two fixes verbatim** — it would fail to find `translation_service.py` at that path. Use:

```yaml
  translation-service:
    build:
      context: ./translation-service
      dockerfile: Dockerfile
    ports:
      - "5030:5030"
    environment:
      - DB_HOST=postgres-2
      - DB_NAME=audiotours
      - DB_USER=admin
      - DB_PASSWORD=password123
      - DB_PORT=5432
    restart: unless-stopped
```

**Also important:** `translation_service.py` defaults `DB_HOST` to `development-postgres-2-1` (its own internal default, line 31), not `postgres-2` (the actual compose service name / network alias). Without the explicit `DB_HOST=postgres-2` override above, it likely can't resolve the database host on the compose network — same class of trap as the orchestrator's own explicit `DB_HOST` override. Also needs AWS credentials (it imports `boto3`) — add `env_file: [.env]` the same way `polly-tts-1` did, or explicit `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` entries, whichever pattern the rest of the compose file has settled on.

**Verify:** rebuild, `curl http://localhost:5030/health` (check the file for the actual health-check route name), then re-run the Russian translation request from the app and confirm it completes instead of "Connection refused."

---

## Issue 2 — Listen Page title says "Museum" while everything else (coordinates, content, icons) correctly used "Walking"

This is not a UI bug — the mismatch is baked into the generated content itself, at the source.

**Root cause, confirmed in `generate_tour_text.py`:**
```python
# PHASE 6, ~line 3235
if tour_type.lower() in location.lower():
    tour_title = f"Step-by-Step Audio Guided Tour: {location}"
else:
    tour_title = f"Step-by-Step Audio Guided Tour: {location} - {tour_type.title()} Tour"

complete_tour = tour_title + "\n" + f"Tour-Category: {tour_category}" + "\n\n"
```

The **title** uses `tour_type` — the raw, unsuppressed, client-supplied value, which is still `"museum"` for this request (the iPhone app's own request parser has no branch for "camelback riding" and defaults to `tour_type: "museum"`, exactly as documented back in `KIRO_REVIEW_01`). Everything else in the pipeline (stop selection, GEO-CHECK tier, icons) correctly uses the internally-corrected `tour_category` (`"walking"`) — but this one line, building the human-visible title text embedded in the tour content, was never updated to match. The `Tour-Category: {tour_category}` line right below it *does* use the correct value, but that's an internal metadata line, not the display title.

This is very likely also why `manifest.json` (bundled in the delivered ZIP — see `KIRO_REVIEW_03`'s ZIP inspection: `"name": "Palais Lascaris... - Museum Tour"`) carries the same wrong label — check whether `tour_generation_modernized.py` derives the manifest name from this same title string or reconstructs it separately; fix wherever it's actually sourced from.

**Fix:**
```python
_display_category = tour_category.replace('_', ' ').title()
if tour_type.lower() in location.lower():
    tour_title = f"Step-by-Step Audio Guided Tour: {location}"
else:
    tour_title = f"Step-by-Step Audio Guided Tour: {location} - {_display_category} Tour"
```
Check every other place in the file that builds a user-facing string from `tour_type` instead of `tour_category` — this pattern (title construction predating the classification fixes, never updated) may not be limited to just this one line. Grep for `tour_type` usages that produce display text, as distinct from the ones that are supposed to stay as the raw client value (e.g., logging, the original `[Bug2Fix]` suppression logic itself).

**Verify:** regenerate the camel tour, confirm the title text (and manifest.json's `name`, if that's the same source) reads "Walking Tour," not "Museum Tour," while everything else stays correct.

---

## Issue 1 — only 2 of 4 stops were actually reachable by camelback

This is different in kind from the other two — it's a content-quality gap, not a classification or wiring bug, and it's inherent to what the fix in `KIRO_REVIEW_07`/`08` was actually designed to do. That work fixed *how far apart stops are allowed to be*; it never touched *what makes a candidate stop suitable for the stated mode of travel*. A camel tour and a walking tour currently ask the AI for candidate points of interest the same way — nothing tells it "these need to be reachable by camel," so it's free to suggest, e.g., a building interior or a paved shopping district stop that a camel route wouldn't sensibly include.

### Two-part fix: a constraint prompt (raise the odds) + a cheap verification call (actually check), scoped only to genuinely unusual modes

**Part A — prompt constraint, same precedent as museum's single-venue constraint:**
```python
# ~line 1723, PHASE 3A — museum's existing pattern, for reference
if tour_category == 'museum':
    _museum_venue_constraint = (
        f"CRITICAL CONSTRAINT — THIS IS A SINGLE-VENUE MUSEUM TOUR..."
        ...
    )
```
Add the equivalent for non-`on_foot` modes:
```python
_TRANSPORT_STOP_CONSTRAINT = {
    'animal': "This is a CAMELBACK/HORSEBACK tour. Every stop MUST be reachable on horse/camel-back "
              "along an outdoor route (trails, dunes, oases, open landscape). Do NOT suggest stops that "
              "require entering a building, a paved shopping district, or any location primarily accessed "
              "by car — those are not reachable as part of this ride.",
    'bike': "This is a BIKING tour. Stops should be reachable via bike paths, roads, or trails suitable "
            "for cycling — avoid stops requiring highway travel or building interiors inaccessible by bike.",
    'vehicle': "This is a DRIVING tour. Stops should be reachable by car and have parking or roadside access.",
}
if transport_mode in _TRANSPORT_STOP_CONSTRAINT:
    # fold into the PHASE 3A prompt the same way _museum_venue_constraint is folded in today
    ...
```
This alone is what I originally proposed — a nudge, not a check. On its own it wasn't good enough: nothing was verifying the AI actually complied.

**Part B — the actual fix, from the user's suggestion: a cheap, narrowly-scoped verification call, giving this real teeth the way museum tours already have behind their constraint.** Only run it for genuinely unusual modes — not walking, not biking, not driving, all of which are common enough that the prompt constraint alone is adequate and a verification call would be overkill:

```python
_UNUSUAL_TRANSPORT_MODES = {'animal'}  # camel/horseback only, for now — extend later if another
                                         # genuinely unusual mode shows up (e.g. boat tour)

def _verify_transport_accessibility(poi_list, transport_mode, location, api_key):
    """For unusual transport modes only, ask a single cheap AI call which candidate
    stops are NOT plausibly reachable via the stated mode. Advisory: on any failure,
    keep all stops — never crash, never empty the tour."""
    if transport_mode not in _UNUSUAL_TRANSPORT_MODES:
        return poi_list  # no-op for common modes — this is the cost control

    stop_list_str = "\n".join(f"- {p['name']} ({p.get('address', '')})" for p in poi_list)
    prompt = f"""These are candidate stops for a {transport_mode} tour in {location}.

Which of these stops would NOT be plausibly reachable as part of a {transport_mode} route
(e.g. inside a building, a shopping mall or paved commercial district, or a location that
would realistically require a car to reach)?

Stops:
{stop_list_str}

Return ONLY a JSON array of the stop names to EXCLUDE. Empty array if all stops are fine."""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-3.5-turbo",  # same cheap tier already used for intent analysis, replacement stops, etc.
                "messages": [
                    {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 200,
            },
            timeout=15,
        )
        if response.status_code == 200:
            excluded_names = json.loads(response.json()["choices"][0]["message"]["content"])
            if excluded_names:
                print(f"  [TRANSPORT-VERIFY] Excluding {len(excluded_names)} stop(s) not reachable by {transport_mode}: {excluded_names}")
            return [p for p in poi_list if p['name'] not in excluded_names]
    except Exception as e:
        print(f"  [TRANSPORT-VERIFY] Verification failed (advisory, keeping all stops): {e}")
    return poi_list  # fail permissively — same posture as GEO-CHECK and PHASE 3C
```

Call this right after PHASE 3A produces `poi_list` (with Part A's constraint already applied), before GEO-CHECK runs. **One open design question to resolve while implementing, not before:** if stops get excluded here, should the tour proceed with fewer stops, or should this hook into the *same* replacement-fetching flow GEO-CHECK already has (fetch N more candidates to backfill)? Reusing that existing replacement logic is probably right — don't build a second one from scratch — but confirm the plumbing (it currently lives inside the GEO-CHECK block, keyed to that specific outlier-removal flow) before assuming it's a drop-in call.

**Cost:** negligible by construction — one small batched call (not per-stop), only for `transport_mode == 'animal'`, which is a small fraction of total tour generations. No cost concern here worth optimizing further.

**Verify:** regenerate the camel tour, confirm `[TRANSPORT-VERIFY]` actually excludes implausible stops (test this by including an obviously-wrong candidate, e.g. a shopping mall, in a manual test if PHASE 3A doesn't naturally produce one), and confirm walking/bike/vehicle tours show no `[TRANSPORT-VERIFY]` log line at all (cost-control check — this must not silently start running for common modes).

---

## Priority for this round

1. Translation service (Issue 3) — same fix pattern as twice before, low risk, clear win.
2. Title mismatch (Issue 2) — small, precise fix, directly addresses something a real user noticed and found confusing.
3. Stop-suitability (Issue 1) — do this one last; Part A (prompt constraint) is quick, Part B (verification call) needs the replacement-stop plumbing question resolved, and both need real output review, not just a clean pass/fail check.

Report back with the same evidence standard as every round: actual rebuild, actual regenerated tour, actual title text and translation result — not a description of what should happen.
