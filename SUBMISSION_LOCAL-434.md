# SUBMISSION_LOCAL-434.md

## 1. MFA Unbound Variance — Real Pipeline Measurement

**Result: 0/5 runs produced a tour. story_count variance is unmeasurable because the
pipeline never reaches content generation.**

### What happened (5/5 runs identical):

1. Intent analysis calls GPT-4o, which returns JSON wrapped in markdown fences (`\`\`\`json ... \`\`\``)
2. `json.loads()` fails on both attempts — intent = None
3. Without intent, `venue_name` is not extracted
4. BLOCKER4a location-fallback checks first comma segment of "Picasso, Miro, Dali: ..." → "Picasso" — no museum keyword found
5. Without `_museum_venue_name`, the exhibition checklist path is never invoked
6. Phase 3A asks GPT for 6 "contained stops" near MFA with no venue constraint
7. GPT returns 6 scattered Boston venues (Gardner Museum, Fenway Park, BPL, Copley Square, ICA, Esplanade)
8. BLOCKER4b detects 5–6 distinct addresses for 6 stops → rejects correctly

**Provenance line showing Wayback path engaged: NEVER — the pipeline dies before reaching
`find_exhibition_checklist`, so `_fetch_page` / `_fetch_from_wayback` are never called.**

The Wayback path (D381/D382) works and is verified by `test_local429_wayback_fallback.py`
(passes). The issue is upstream: the intent parser lacks fence-stripping, and without a
parsed intent the museum venue constraint is lost.

### Data (committed as `local434_variance_mfa_unbound.json`):

| Run | Result | BLOCKER4b | Addresses | Elapsed |
|-----|--------|-----------|-----------|---------|
| 1   | FAILED | FIRED     | 6         | 5.2s    |
| 2   | FAILED | FIRED     | 6         | 4.6s    |
| 3   | FAILED | FIRED     | 6         | 5.0s    |
| 4   | FAILED | FIRED     | 6         | 4.8s    |
| 5   | FAILED | FIRED     | 5         | 5.9s    |

Per-stop story_count: N/A (no tour generated)
All-stops-pass frequency: 0/5 (0%)
Mean/min/max/stdev: N/A

---

## 2. BLOCKER4b Verdict: REAL (not an artefact of the pin)

**BLOCKER4b fires on the unpinned path. It is a real property of the MFA route.**

But the root cause is NOT "6 works inside one museum resolve to 6 distinct addresses"
(which would be a geocoding problem). The actual mechanism is:

- Without the venue_name constraint, Phase 3A's prompt does not tell GPT "list artworks
  inside MFA." It asks for generic "contained stops" and GPT interprets this as "venues
  near MFA Boston."
- The 6 POIs returned are **6 different buildings** (MFA, Gardner, Fenway, BPL, ICA,
  Esplanade) — they genuinely have 6 different addresses.
- BLOCKER4b is correctly rejecting these as "a city-wide museum tour, not interior rooms."

**Why LOCAL-433 saw the same thing under the pin:** The pin bypasses
`find_exhibition_checklist` but does NOT supply `_museum_venue_name`. So even with
the pin, Phase 3A still falls through to the generic prompt, still gets scattered
venues, and BLOCKER4b still fires. The pin was masking the *Wayback path* (correctly),
but it was also masking the fact that the venue_name propagation is broken for this
location string (incorrectly — that's what produced the "unmeasurable" finding).

**Summary:** BLOCKER4b is real and correct. The underlying problem is intent
parsing + venue_name propagation, not geocoding.

---

## 3. Stale Pin Audit

### Files checked:

| File | 429 Premise | Verdict | Action |
|------|-------------|---------|--------|
| `run_mfa_unbound_pinned.py` | "mfa.org returns HTTP 429 to every request" | **STALE.** D381 merged the Wayback fallback; the venue is reachable. Header explicitly says "This is not proof that the pipeline can find the exhibition." | **DELETE** — the premise is false since LOCAL-429 merged, and the pin bypasses the production path that now works. |
| `run_local433_mfa_unbound_variance.py` | "mfa.org returns HTTP 429, so without the captured page bytes the tour cannot resolve its works" | **STALE.** Same false premise as above, copied from `run_mfa_unbound_pinned.py`. Monkeypatches `find_exhibition_checklist` → Wayback path never engages → produced the false finding in D386. | **DELETE** — this is exactly the "helper that silently bypasses a merged fix" D387 describes. |
| `run_local252_corpus_depth.py` | `WIKI_DELAY = 3.0 # seconds between requests to avoid 429` | **CURRENT.** This is about Wikipedia's MediaWiki API rate limits, not mfa.org. The 3-second delay between Wikipedia fetches is standard practice. No monkeypatching, no bypass. | **KEEP** — premise is valid and unrelated to the MFA issue. |

### Action taken:

- `run_mfa_unbound_pinned.py` — **deleted**
- `run_local433_mfa_unbound_variance.py` — **deleted**
- `run_local252_corpus_depth.py` — kept (valid premise, different endpoint)

---

## 4. Control (D302/D326): Palais Lascaris

**PASS** — one live run.

| Check | Result |
|-------|--------|
| Stops | 4/4 ✓ |
| Dates | 1780, 1652, 1581, 1696 — all intact ✓ |
| Coordinates | 4/4 ✓ |
| story_count | 2/2/3/2 (gate 1/4 — consistent with D385/D386 variance) |

Committed as `local434_palais_control.json`.

---

## 5. Neutralisation (D242 #1, D277, D376)

Module scope: `variance_harness.compute_statistics` and `variance_harness.compute_gate_verdicts`
are the production symbols used by the runner. Neutralising each in place:

### compute_statistics neutralised → 7 tests RED:

```
FAILED test_single_value - assert 0 == 5.0 (mean)
FAILED test_two_values - assert 0 == 3.0 (mean)
FAILED test_three_values_from_task - assert 0 == 1.67
FAILED test_five_identical_values - assert {'count': 0, ...} == {'count': 5, ...}
FAILED test_five_values_known - assert 0 == 3.0
FAILED test_empty_raises - DID NOT RAISE ValueError
FAILED test_zeros - assert {'count': 0} != {'count': 3}
```

### compute_gate_verdicts neutralised → 4 tests RED:

```
FAILED test_d385_table_data - assert 0 == 3 (total_runs)
FAILED test_all_pass - assert 0 == 2 (all_pass_count)
FAILED test_empty_raises - DID NOT RAISE ValueError
FAILED test_mixed_stop_counts - KeyError: 'A' (per_stop_pass_rate empty)
```

Restored → 12/12 green.

---

## 6. Targeted suites green

```
tests/test_local433_variance_statistics.py — 12 passed
tests/test_local429_wayback_fallback.py — 16 passed
tests/test_local430_wayback_staleness.py — 10 passed
tests/test_local431_story_gate_enforcement.py — 6 passed
tests/test_local364_exhibition_checklist.py — 30 passed
Total: 62 passed, 0 failed
```
