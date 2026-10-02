# SUBMISSION — LOCAL-474: An Unrecognised Request Must Not Be A 400

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-474-empty-tour-type`
**Base:** `storied` @ `bd109fa` (verified `git merge-base --is-ancestor bd109fa HEAD` → exit 0)
**Scope:** SERVER half only. `audio_tour_app/` untouched (that is Mobile Kiro's half).

---

## The defect

The app sends `tour_type: ''` whenever it recognises no category keyword
(`tour_request_parser.dart:111` — "let the server decide"). There is no
`restaurant`/`food`/`bar`/`café`/`brewery` branch in the parser, so every
restaurant request — the headline of the Storied release — arrived with an
empty `tour_type`. The server did not decide; it rejected:

```python
if not location or not tour_type:      # not '' is True
    return jsonify({"error": "location and tour_type are required"}), 400
```

That exact payload 400'd in production on 2026-09-03.

The generator **already** classifies category from the request text
(`_classify_tour_category` in `generate_tour_text.py`). The only thing standing
in the way was the validation gate. This change makes the parser's comment true:
an absent/empty `tour_type` means **"classify it"**, not "400".

---

## What changed

Three files, ~90 lines. No behaviour change for requests that already worked.

### 1. `tour_orchestrator_service.py` — relax the gate (require `location` only)
The `/generate-complete-tour` gate now requires `location` only. An empty
`tour_type` is logged and passed downstream to the classifier. The `location`
check is unchanged and still 400s (AC3). The separate `user_id`/quota gates are
untouched.

### 2. `generate_tour_text_service.py` — relax the mirror gate + normalize
The `/generate` gate had the **same** `not location or not tour_type` check. It
had to change too — otherwise the orchestrator would forward `''` and be
rejected one hop later. Also `tour_type = data.get('tour_type') or ''` so a
missing key arrives as `''` rather than `None`.

### 3. `generate_tour_text.py` — infer, log, and clean-fail
- **Normalize** `tour_type is None → ''` at function entry (downstream calls
  `tour_type.lower()` and `f"{tour_type} {location}"`, both of which crash on
  `None`).
- **Inferred-category log** at the point category is finalized (right where
  `Detected tour category:` is printed, alongside the params logged at
  `GENERATE_TOUR_TEXT_FUNCTION_ENTRY`):
  ```
  [LOCAL-474] tour_type='' -> category='restaurant' (source=inferred)
  ```
  `source=inferred` when `tour_type` was empty, `source=explicit` otherwise —
  so a wrong inference is visible in the tour log rather than silent.
- **Clean-fail guard**: if classification ever collapses to empty/None (a
  genuinely unclassifiable request), the function returns
  `None, None, (None, None)` and sets `_LAST_CLEAN_FAIL_EVIDENCE` with
  `error_type="unclassifiable_request"` and a useful `user_message`. This reuses
  the existing degradation-evidence mechanism the service layer already surfaces
  (same path as `exhibition_closed` / `exhibition_not_found`). A well-formed
  request that cannot be classified gets a helpful message — **not** a generic
  400, and **not** a tour about nothing.
- Two small pure helpers, `_infer_category_log_line()` and
  `_build_unclassifiable_evidence()`, are pulled out so the log format and the
  clean-fail evidence are unit-testable without driving the whole pipeline.

**Scoping note:** the guard assigns the module globals `_LAST_CLEAN_FAIL_EVIDENCE`
and `_LAST_GENERATION_COST`. `generate_tour_text()` already declared
`global _LAST_GENERATION_COST` at the top and `global _LAST_CLEAN_FAIL_EVIDENCE`
later. I hoisted the clean-fail `global` to the top declaration block and removed
the now-redundant later one (Python forbids a `global` after the name is already
assigned in the function). Verified with `py_compile`.

---

## Acceptance criteria — evidence

All verified against the **live local container** (per D242, `exit=0` proves
nothing). Because the running images are baked from a divergent, older tree, I
`docker cp`'d the *same three edits* into the running `audioura-tour-generator-1`
and `audioura-tour-orchestrator-1` containers, restarted them (no image rebuild —
disk was tight), tested, then **restored the containers to their baked state**
and cleaned up all temp files.

### AC1 — empty `tour_type` accepted and classified restaurant
```
POST http://localhost:5000/generate
  {"location":"Bread Thyme restaurant tour in West Roxbury, MA","tour_type":"","total_stops":1}
→ HTTP 200 {"job_id":"c8d62ce9-...","status":"queued"}
```
Before the fix this exact payload returned
`{"error":"location and tour_type are required"}` (HTTP 400).

The tour log (`api_call_chain_20260914_222121.txt`) shows it classified as a
restaurant tour:
```
CALL #007 PHASE_3A_REQUEST  poi_type_hint: restaurants
CALL #008 OPENAI_API_CALL   prompt: "...CRITICAL CONSTRAINT — THIS IS A RESTAURANT/DINING TOUR..."
            response: West on Centre / Corrib Pub and Restaurant / Porters Bar and Grill  (real West Roxbury restaurants)
```

**Inferred-category log line** (captured from the live patched container code):
```
[LOCAL-474] tour_type='' -> category='restaurant' (source=inferred)
```

Orchestrator end-to-end with a `user_id` (past all gates):
```
POST http://localhost:5002/generate-complete-tour
  {"location":"Bread Thyme restaurant tour in West Roxbury, MA","tour_type":"","total_stops":1,"user_id":"local474-test","request_string":"bread thyme"}
→ HTTP 200 {"job_id":"a726ea74-...","status":"queued","language":"en"}
```
And the old message is gone:
```
POST /generate-complete-tour {"location":"X","tour_type":"",...}  → OLD MESSAGE GONE (GOOD)
```

### AC2 — explicit `tour_type` unchanged
`_classify_tour_category("Nice, France", "restaurant") == "restaurant"`,
`_classify_tour_category("Some City", "museum") == "museum"`, and the log line
reports `source=explicit`. An explicit type still wins.

### AC3 — missing `location` still 400s
```
POST /generate-complete-tour {"tour_type":"walking","total_stops":1,"user_id":"u1"}
→ HTTP 400 {"error":"location is required"}
```
Also verified at the generator: missing/empty `location` → 400.

### AC4 — break it, show the test go red, prove clean-fail
The clean-fail guard is unit-tested via the extracted seam. Demonstrated
red → green by temporarily corrupting `error_type` in
`_build_unclassifiable_evidence`:
```
# guard broken:  error_type = "WRONG_TYPE_BREAKAGE"
FAILED tests/test_local474_empty_tour_type.py::...::test_green_guard_fires_with_typed_evidence
  AssertionError: 'WRONG_TYPE_BREAKAGE' != 'unclassifiable_request'
# guard restored:
1 passed
```
Live container confirms the clean-fail produces a useful message, not a 400:
```
_build_unclassifiable_evidence("???","") →
  error_type = unclassifiable_request
  user_message = 'We could not tell what kind of tour "???" should be. Try naming a
                  place, neighborhood, or a tour type (e.g. "restaurant", "walking", "museum").'
```
And a well-formed-but-thin request fails cleanly through the existing evidence
path (observed for the Bread Thyme run when knowledge was insufficient):
`"...no stops could be generated (all filtered or knowledge insufficient)."` —
never a tour about nothing.

### AC5 — ran against the local container, not only unit tests
See AC1/AC3 above. Container was restored to baked code afterwards; verified the
old 400 behaviour returns after restore.

---

## Tests

`tests/test_local474_empty_tour_type.py` — 13 tests, all passing:
- classifier accepts empty type → restaurant; never yields empty category
- explicit type wins (AC2)
- inferred-category log format (inferred vs explicit, None handling)
- clean-fail guard: typed evidence, useful message, red→green (AC4)
- HTTP gate via Flask `test_client`: empty/missing `tour_type` accepted (200),
  missing/empty `location` → 400 (AC1/AC3)

```
13 passed in 0.26s
```
`py_compile` clean on all three modified modules.

---

## NOT in this change
- `audio_tour_app/` — the mobile parser fix (adding `restaurant` and friends, and
  not sending `''`) is Mobile Kiro's separately-filed half. The two fixes are
  independent; either alone is an improvement.
- No Docker images rebuilt (disk constraint). No protected files edited
  (`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `PENDING_REMINDERS.md`, `BUILD_NUMBERS.md`).
