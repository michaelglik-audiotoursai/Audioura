# SUBMISSION — LOCAL-767 (+ LOCAL-275)

**Branch:** `LOCAL-767-venue-parts-degrade`
**Base:** `storied` @ `354da345` (verified `git merge-base --is-ancestor 354da345 HEAD` → exit 0)
**Agent:** Mac Mini Kiro

> A church / civic building / facility tour must not hard-fail when Gemini returns
> nothing. A missing or exhausted Gemini key (prepaid balance!) must never take out
> a whole CLASS of tours.

---

## The field failure (GCloud_Storied, 2026-10-25 17:3x, ClickUp wdvrdaz5vd)

`POST /generate-complete-tour {"location":"Newton City Hall, Newton, MA","tour_type":"landmark","total_stops":1}`
failed on `tour-generator-storied`. Newton City Hall is a `worship_civic` venue, so
`generate_tour_text` took the venue-parts path and called
`venue_parts.build_tour_stops()`, whose `default_ask` is
`story_leads.gemini_with_sources()`. With **no usable Gemini key** every ask returned
`''`, the D577 outage guard raised `ServiceUnavailable`, **and the caller re-raised
it** — taking out the whole tour. Beta generated these venues fine because it had no
venue-parts path.

Separately (LEAD add): `tour-generator-storied` v4 / `d25454a` logged
`[LOCAL-275] Part 2 error: name _venue_parts_used is not defined` — the tour still
completed, but Part 2 (the closing offer) was silently truncated.

---

## What changed — `generate_tour_text.py` only

### 1. LOCAL-767 — the caller degrades instead of aborting (the fix)

The venue-parts caller's `except venue_parts.ServiceUnavailable` block used to print
a `*** SERVICE UNAVAILABLE — ABORTING ***` banner and `raise`. It now **catches the
outage, logs it LOUDLY, and falls back to the standard (non-venue-parts) stop path**
that Beta used, leaving `_venue_parts_used = False` so every downstream branch takes
its ordinary route:

```
[LOCAL-767] venue-parts unavailable (reason=…) — falling back to standard stops
```

The generic `except` was given the same loud-degrade treatment.

**Why this honours D577 AND D582 rather than overriding them.** `build_tour_stops`
**still RAISES** `ServiceUnavailable` — the outage signal is deliberately kept, because
D582's rule is that an outage must stay distinguishable from "this venue has nothing
to describe" (the silent fallback that scored clean and fooled LEAD for half a day).
The only thing that changed is the **caller's response**: from "abort the whole tour"
to "log the outage by reason and continue on the standard path". That is exactly
D577's product philosophy — *"providing an uninteresting stop is better than
providing no stop… all we have to do is be clear and transparent"* — applied to an
outage: the degrade is LOUD, never silent.

**D577's own written case is preserved.** The honest-refusal exception still exists
and still fires for the case it was written for: a **reported, inspectable** outage
(the `ServiceUnavailable` is raised and logged, not swallowed into a `[]` that looks
like a healthy empty answer). A venue that is genuinely undescribable while the
service is **live** still degrades to `[]` without raising — proven by test #3 below.

### 2. LOCAL-767 — startup key-presence log

One line, early in `generate_tour_text`, stating the one fact that explains every
"Gemini silently did nothing" bug — **never the value**:

```
[LOCAL-767] GEMINI key present=<bool>
```

### 3. LOCAL-275 — the `_build_closing_offer` NameError(s)

`_build_closing_offer` is a module-level function that referenced `_venue_parts_used`
— a **local of `generate_tour_text`**, invisible from here — so Part 2 raised
`NameError`, caught and printed as `Part 2 error: name _venue_parts_used is not
defined`, truncating the closing offer. Fixing that surfaced a **second** undefined
name in the same function: `tour_type`, used by
`_detect_venue_class(location, tour_type)`.

Both are now parameters (`venue_parts_used=False`, `tour_type=""`), passed at the call
site alongside the already-correct `_build_closing_recap(..., distance_meaningful=not
_venue_parts_used)`.

### Gemini-call audit (acceptance #2)

Every Gemini call on the generation path was classified:

| site | without a key | verdict |
|---|---|---|
| `story_leads._gemini` | returns `''` | degrades |
| `story_leads.gemini_with_sources` | returns `{error:'no GEMINI_API_KEY', text:''}` | degrades |
| `story_leads._openai` | returns `''` | degrades |
| `venue_parts.default_ask` → `gemini_with_sources(grounded=False)` | `''` | degrades |
| `venue_parts.default_ask_grounded` | `('', [])` | degrades |
| `venue_parts.build_tour_stops` | raises `ServiceUnavailable` (outage SIGNAL, by design) | raised, now caught at caller |
| **`generate_tour_text` venue-parts caller** | **re-raised → whole tour died** | **FIXED → loud degrade** |
| `tragedy_context_gate` asks (lines ~18917, ~19776) | grounded returns `('', [])`; content-level only | degrades (no whole-tour fail) |

The venue-parts caller was the **only** whole-tour hard-fail. It is fixed.

---

## Tests — `test_local767_venue_parts_degrade.py` (9 tests)

RED on the baseline, GREEN on the branch. Offline/deterministic (every model call
into `venue_parts` is injected; the caller behaviour is asserted by source
inspection, the LOCAL-485 pattern, because `generate_tour_text` makes network calls).

| # | test | baseline 354da345 | branch |
|---|---|---|---|
| 1 | empty ask + dead probe still RAISES `ServiceUnavailable` (signal kept, D582) | ✅ pass | ✅ pass |
| 2 | caller handler does **not** re-raise | ❌ fail | ✅ pass |
| 2 | caller handler logs the `[LOCAL-767] … falling back to standard stops` line, no ABORT banner | ❌ fail | ✅ pass |
| 2 | caller handler sets `_venue_parts_used = False` | ❌ fail | ✅ pass |
| 3 | **live** service + genuinely-absent venue degrades to `[]`, never raises (D577 case intact) | ✅ pass | ✅ pass |
| 4 | `_build_closing_offer` has a `venue_parts_used` parameter | ❌ fail | ✅ pass |
| 4 | body no longer names the undefined global | ❌ fail | ✅ pass |
| 4 | Part 2 builds a closing offer for `venue_parts_used ∈ {True, False}` — no NameError | ❌ fail (TypeError) | ✅ pass |
| 5 | generator logs `[LOCAL-767] GEMINI key present=` as a bool, never the value | ❌ fail | ✅ pass |

**Baseline: 2/9 pass, 7 fail** (the 2 passing are the preserved-contract guards #1 and
#3 — they must pass on both trees, proving the fix did not break the outage signal or
over-correct the D577 case). **Branch: 9/9 pass.**

Baseline directly reproduces the field error:

```
$ python3 -c "import generate_tour_text as g; g._build_closing_offer([...],'facility','walking','Newton City Hall, Newton, MA',sentence_budget=3)"
  [LOCAL-275] Part 2 error: name '_venue_parts_used' is not defined
```

**Existing suites still green on the branch:**
`test_local528` 15/15 · `test_local485` 21 OK · `test_venue_identity` 16/16 ·
`test_local496` 10 OK. `generate_tour_text.py` `py_compile` OK.

---

## Live test — `run_local767_live.sh` / `run_local767_live.py`

Disposable container **`local767-gen`** (never `-p audioura`, never an `audioura-*`
container), `Dockerfile.generator`, network `development_default`, shared
`postgres-2`. Metered to `/meterlogs/paid_api_calls.jsonl`. Per-tour OpenAI cap
`$0.40`. `"Newton City Hall, Newton, MA"`, 1 stop, run twice.

**RUN 1 — GEMINI_API_KEY and GOOGLE_API_KEY unset:**
```
[LOCAL-767] GEMINI key present=False
[LOCAL-767] venue-parts unavailable (reason=…the model service is unavailable… probe='') — falling back to standard stops
OUTCOME: TOUR DELIVERED — 2245 chars, 1 stop (Council chambers)
delivered=True  fell_back=True  ABORTED=False  venue_parts_fill=False
```

**RUN 2 — GEMINI key present:**
```
[LOCAL-767] GEMINI key present=True
[D571] VENUE-PARTS FILL  (venue-parts path used)
OUTCOME: TOUR DELIVERED — 2194 chars, 1 stop   (4 grounding requests)
delivered=True  venue_parts_fill=True
```

**LOCAL-767 LIVE: PASS.**

- **Total metered spend: `$0.2564`** (≤ `$0.80`). OpenAI `$0.0455` + grounding `$0.1400`
  for RUN 2; RUN 1 made no paid grounding calls (keyless).
- **DB (D141):** `audio_tours` BEFORE = AFTER = **523 total, 439 is_test** — the
  harness calls `generate_tour_text` directly, which does not write `audio_tours`, so
  **zero rows written and nothing deleted**. ("lat/lng NULL" is N/A — no rows were
  created; the harness does not pollute the shared DB at all.)
- No `audioura-*` container touched; `audioura-tour-generator-1` still healthy. Image
  `local767-gen-img` removed; no lingering container.

Full log (gitignored): `tours/local767_live/local767_live.log`.

---

## Process / scope

- Branched from local `storied` HEAD `354da345` (not `origin/storied`, per D358).
- Committed in small steps, never `git add -A` (only named files).
- Did **not** touch `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
  `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`,
  `GCLOUD_STORIED_START_HERE.md`.
- **No new Python module** — only edits to existing `generate_tour_text.py` plus a new
  test file and the live harness. Both generator Dockerfiles (`Dockerfile.generator`,
  `Dockerfile.local22`) use bulk `COPY *.py /app/`, so nothing needs a per-file line;
  the one-by-one-copy Dockerfiles are for other services and reference neither
  `generate_tour_text.py` nor `venue_parts.py`.

## Files

| file | change |
|---|---|
| `generate_tour_text.py` | venue-parts caller degrades (not aborts); startup key-presence log; LOCAL-275 param fixes |
| `test_local767_venue_parts_degrade.py` | new — 9 tests, red on baseline / green on branch |
| `run_local767_live.py`, `run_local767_live.sh` | new — isolated-container live harness |
