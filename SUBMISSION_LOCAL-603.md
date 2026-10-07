# SUBMISSION — LOCAL-603: Venue preflight (D618)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-603-venue-preflight` (base `subscribed` @ 21b9eba)
**Base verified:** `git merge-base --is-ancestor 21b9eba HEAD` → exit 0.

## What this does

Every **single-venue** request (a named museum / restaurant / attraction) now starts
with **one grounded Gemini call** — the *venue preflight* — before any generation
spend. Its answer is used two ways:

- **A gate.** Permanently closed (or temporarily closed with no reopen date) →
  stop before any further spend, with `error_code=venue_closed`, a plain message
  and an actionable suggestion. This is the guard that would have caught the WNDR
  Museum Boston embarrassment (permanently closed 2026-08-30, which we shipped a
  "tour" of).
- **Plan B material.** When our own sources (Wikidata/Wikipedia, the official
  site, Serper) give no hours, no admission, or fewer than N stops, the
  preflight's sourced facts fill the gap — each with its grounding source URL,
  never unsourced.

Measured preflight cost on the live run: **$0.042 per call** (1 grounded request,
3 Google search queries at $0.014) — inside the ruling's $0.02–0.05 estimate and
well under 3% of a $1.50 museum tour.

## Deliverables

### 1. `venue_preflight.py`
`preflight(venue, city) -> dict`. Strict JSON result: `status`
(open / temporarily_closed / permanently_closed / unknown), `closed_since`,
`address`, `hours` (with days), `admission`, `current_exhibitions_or_highlights`
(list of `{title, artist?, note}`), plus per-field `sources` (grounding chunk
URLs) and the de-duped `grounding_sources` list.

- **One grounded call** through `story_leads.gemini_with_sources(grounded=True)`,
  so the LOCAL-594 meter counts it.
  - *Why two prompts, one grounded call:* measured against `gemini-flash-latest`,
    a prompt that **demands JSON** makes the model answer from memory and NOT
    search (empty `webSearchQueries`, zero chunks, and it even hallucinated WNDR's
    year as 2024). A **natural-language question** reliably triggers 2–3 searches
    and returns real source URLs. So the one grounded call asks the NL question
    (billable, counted), and a cheap **ungrounded** call reshapes that grounded
    prose into strict JSON (Flash tokens only, not counted on the grounding
    channel). The closure guard checks the grounded answer's **sources**.
- **7-day DB cache** per `(venue, city)` in a small additive table
  `venue_preflight_cache` (nothing DROPs/DELETEs; a stale row is TTL-ignored and
  overwritten on refresh). A cache hit makes **no grounded call**.
- **Respects the L2 guard:** `GroundingForbiddenError` propagates out of
  `preflight` (an L2 by-reference build must never spend on grounding);
  `safe_preflight` turns it into an explicit `{'skipped': 'l2_by_reference'}`
  marker with zero grounded requests.

### 2. Closure gate
`gate(venue, city, result)` returns a structured `venue_closed` refusal for
`permanently_closed`, and for `temporarily_closed` **only when there is no reopen
date**. **False-closure guard (D539 applied):** a closed status is honoured only
when **≥ 1 grounding source** (title/URL) carries a closure word; otherwise the
status is downgraded to `unknown` and generation continues (absence of evidence
must never refuse a live venue). Confirmed closures are recorded through the
existing `known_closed_venues.json` mechanism (prints `[PREFLIGHT] NEW CLOSED
ENTRY …` and best-effort appends), so the next request skips the call entirely.

User-facing copy (WNDR): message *"WNDR museum in Boston closed permanently on
August 30, 2026."*, suggestion *"Try a nearby museum, or a walking tour of the
area."*

### 3. Plan B wiring (`generate_tour_text.py`)
- The gate runs in the **wrapper** `generate_tour_text`, **before** the stop-pool
  fast path and `_generate_tour_text_impl`, so a closed venue is refused with
  **zero** downstream spend. `generate_tour_text_service.py` surfaces
  `error_code=venue_closed` with its message/suggestion/sources verbatim
  (terminal, like `by_reference_no_material`).
- **D611 opening section:** when the site/OSM gave no hours/admission, the
  preflight's hours/admission are folded into Stop 1 and **spoken**; the source
  goes in the **text view only** (D617) and is carried into the practical-facts
  provenance (D538), never read aloud.
- **Site-first / exhibition path:** when our own extraction yields `< N` stops,
  the preflight's current exhibitions/highlights are added as stop **candidates**,
  each carrying its grounding **source URL** as the seed for the normal story
  pipeline (never unsourced).

### 4. Tests — `tests/test_local603_*.py` (Gemini wire stubbed)
`test_local603_preflight.py` + `test_local603_meter_and_l2.py` cover all six
required cases:

| # | Case | Covered by |
|---|------|-----------|
| 1 | WNDR answer → `venue_closed`, exactly one grounded call, nothing after | `test_wndr_permanently_closed_gates`, `test_known_closed_short_circuits_with_zero_calls` |
| 2 | An open museum with hours → hours spoken in Stop 1 (source in text view only, D617) | `test_open_hours_spoken_source_in_text_only` |
| 3 | Closure claim without a closure-word source → `unknown` and continue | `test_closed_without_closure_source_downgrades` (+ temp-closed gate rules) |
| 4 | An L2 build makes no preflight call | `test_preflight_raises_inside_guard`, `test_safe_preflight_skips_inside_guard` |
| 5 | The meter counts the preflight queries | `test_preflight_increments_requests_and_queries`, `test_two_preflights_accumulate_on_the_meter` |
| 6 | A cache hit makes no call | `test_second_call_served_from_cache` |

Tests are hermetic: the known-closed corpus read/write is patched so no test
pollutes `tests/known_closed_venues.json` (verified clean after every run).

## Test exits (pasted)

```
# LOCAL-603
$ python3 -m pytest tests/test_local603_preflight.py tests/test_local603_meter_and_l2.py -q
14 passed, 1 warning

# referenced suites
$ python3 -m pytest test_local589_*.py -q
25 passed, 1 warning
$ python3 -m pytest test_local592_*.py -q
51 passed
$ python3 -m pytest tests/test_local593* tests/test_local594* tests/test_local595* tests/test_local597* tests/test_local599* tests/test_local600* -q
186 passed, 1 warning
$ python3 -m pytest tests/test_local594_grounding_cost.py -q
10 passed, 1 warning
$ python3 -m pytest tests/test_local596_mirror_in_sync.py tests/test_local596_referral.py tests/test_local596_seats.py -q
21 passed
$ python3 -m pytest tests/test_local596_api.py -q
11 passed
```

**Note on `tests/test_local596_api.py`:** it passes in isolation (11 passed). When
run in the SAME pytest process as many other files it shows 10 failures — this is
pre-existing cross-file test-state pollution (a Flask/DB test client), **not** a
LOCAL-603 regression: verified identical (10 failed, 208 passed) at base
`21b9eba` with the same batch, before any of this ticket's changes.

## Live runs — isolated container `local603-gen` (never any `audioura-*`)

`./run_local603_live.sh` builds `Dockerfile.generator`, runs on
`development_default` against `postgres-2`, OpenAI per-tour cap $1.00, tour cache
off, removes the image at the end. Measured preflight cost per call is reported by
`run_local603_preflight.py` (reads the LOCAL-594 grounding meter and prices the
queries via `cost_rates`).

### RUN 1 — `WNDR museum, Boston, MA`, 7 stops → **venue_closed** (as expected)

```
--- PREFLIGHT (measured, isolated) ---
  status       : permanently_closed
  closed_since : August 30, 2026
  grounding sources: 8
      - https://whatnow.com/boston/local-news/iconic-immersive-art-museum-in-downtown-boston-announces-closure/
      - https://www.cbsnews.com/boston/news/wndr-museum-boston-closing/
      - https://www.bostoncentral.com/wndr-interactive-museum-boston
  PREFLIGHT COST: requests=1 queries=3 $0.0420  (via gemini_with_sources, grounded)
  GATE: venue_closed — WNDR museum in Boston,MA closed permanently on August 30, 2026.
        suggestion: Try a nearby museum, or a walking tour of the area.

[LOCAL-603] VENUE CLOSED GATE: WNDR museum in Boston,MA closed permanently.
OUTCOME: NO TOUR TEXT (refusal/block) after 0.0s
CLEAN-FAIL EVIDENCE JSON:
{
  "error_type": "venue_closed",
  "error_code": "venue_closed",
  "message": "WNDR museum in Boston,MA closed permanently.",
  "suggestion": "Try a nearby museum, or a walking tour of the area.",
  "venue": "WNDR museum",
  "status": "permanently_closed",
  ...
}
Tour total: $0.0000   (gated BEFORE any generation spend)
```

Also recorded for next time:
`[PREFLIGHT] NEW CLOSED ENTRY {"name":"WNDR museum","city":"Boston,MA","expect":"closed","closed_on":"August 30, 2026","ground_truth":"preflight status=permanently_closed … sources: whatnow.com…, cbsnews.com…, bostoncentral.com"}`.

### RUN 2 — `Griffin Museum of Photography, Winchester, MA`, 5 stops → **delivers**

```
--- PREFLIGHT (measured, isolated) ---
  status       : open
  hours        : Tuesday through Sunday, 12:00 PM – 4:00 PM (closed Mondays)
  admission    : General admission is $9 for adults and $5 for seniors … free for members,
                 Winchester residents, and children under 12 … free Thursdays 2–4 PM.
  grounding sources: 6  (artguide.artforum.com, picturingthefuturegmp.org,
                         finditwinchester.org, winchesternews.org, artsfuse.org)
  PREFLIGHT COST: requests=1 queries=3 $0.0420

[LOCAL-603] preflight venue='Griffin Museum of Photography' status=open hours=y admission=y
OUTCOME: TOUR DELIVERED — 13780 chars, 5 stops
Tour total: $0.0000  (served from the LOCAL-590 stop pool; reused=5 new=0)
```

Griffin still delivers; the preflight added **$0.042** to the run (its only new
cost — the tour body reused the pool, so OpenAI was $0.00 this run). Against the
last Griffin run the `Tour total:` delta is therefore the preflight's $0.042.

### Measured preflight cost per call

| request | grounded requests | search queries | $ |
|---|---|---|---|
| WNDR | 1 | 3 | $0.0420 |
| Griffin | 1 | 3 | $0.0420 |

Consistent with the ruling's $0.02–0.05 (1 request, 1–3 queries × $0.014, + Flash
tokens).

## DB report

One small **additive** cache table was created: `venue_preflight_cache`
(`cache_key` PK, `venue`, `city`, `result_json`, `fetched_at`). No DELETE, no
DROP, no GCloud.

```
venue_preflight_cache rows: 2    (WNDR + Griffin, after the live run)
```

## Files

- `venue_preflight.py` — new module (preflight, gate, cache, Plan B helpers,
  known-closed recording, CLI).
- `generate_tour_text.py` — wrapper-level gate before the pool path; Plan B
  practicals (D611/D617) and stop-candidate seeding in the impl.
- `generate_tour_text_service.py` — surfaces `error_code=venue_closed` verbatim.
- `tests/test_local603_preflight.py`, `tests/test_local603_meter_and_l2.py`.
- `run_local603_preflight.py`, `run_local603_live.sh` — isolated-container live
  harness.

## Process

Committed after each step; `git rev-list --count origin/subscribed..HEAD ≥ 1`.
Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
`.continuous_dev/STATUS.md`. No DELETE, no GCloud. Live runs used the disposable
`local603-gen` container only; all `audioura-*` containers were left untouched.
