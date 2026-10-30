# SUBMISSION — LOCAL-843: Activity tours on the cloud

**Base:** subscribed (`d2ad4f74`, contains `2478ad45`) — verified
`git merge-base --is-ancestor d2ad4f74 HEAD` exits 0.
**Branch:** `LOCAL-843-activity-yield`
**Request under test (exact):** `Kitesurf lessons at Mui Ne beach, Vietnam` (5 stops)

The field tour (GCloud_Storied wave 16, gen 00022-kbx, cheap env +
`STORY_PASS_MODEL=gpt-4.1`) shipped **2/5** kite schools, **Gemini $0.16** as the
top line, a header reading **`Tour-Category: restaurant`**, and one invented
story (**"Duc fused kiteboarding and seafood"**). This branch fixes all four.

---

## PASS (live, budget-enforced)

`run_local843_live.py` — `TASK_BUDGET_ID=LOCAL-843 TASK_BUDGET_USD=0.60`, cheap env
+ `STORY_PASS_MODEL=gpt-4.1`, `DISABLE_STOP_POOL=1`, meter contract, Mac-local
no-mount diagnostic (never writes the live DB, never touches the shared
`audioura-*` containers).

```
Kitesurf lessons at Mui Ne beach, Vietnam: 5/5 stops (providers=4, off-category=0)
  title : Step-by-Step Audio Guided Tour: Kitesurf lessons at Mui Ne beach, Vietnam
  header: Tour-Category: places
  Stop 1: Muine Kitesurf School.       [PROVIDER]
  Stop 2: C2Sky KiteSurfing            [PROVIDER]
  Stop 3: Surfpoint Vietnam            [real kite/windsurf school; name-only classifier 'unknown']
  Stop 4: Palm Kite Club Mui Ne        [PROVIDER]
  Stop 5: Mui Ne Bay Kite School       [PROVIDER]
  CHECK providers>=4 : True (4)
  CHECK no off-cat   : True (0)
  CHECK no 'restaurant' label in header/title: True (header='places')
  CHECK no ungrounded 'fused' survivor: True
  GEMINI (status-200): 0 calls  $0.0000
  metered total (status-200): $0.1090 / per-tour cap $0.40 / ledger cap $0.60
=== LOCAL-843 OVERALL: PASS ===
```

| Criterion | Field | This branch |
|---|---|---|
| ≥ 4 real kite providers | 2/5 | **4 providers, 5/5 stops** |
| Gemini $0 | $0.16 | **$0.0000** (0 status-200 gemini rows) |
| No internal category label | `Tour-Category: restaurant` | **`Tour-Category: places`** (title clean) |
| Every story sentence traceable | "Duc fused kiteboarding and seafood" | **ungrounded person/org sentences dropped** |
| ≤ $0.40 | $0.345 | **$0.109** (all Serper) |

---

## The four fixes

### 1. Yield — token family (`category_match_guard.py`)
`requested_activity("Kitesurf lessons …")` returned `tokens=('kitesurf',)` only —
`"kitesurf"` was not a key in `_ACTIVITY_SYNONYMS` (only `kiteboarding` /
`kitesurfing` / `kite` were), so a school named **"Mui Ne Kite School"** or
**"Kiteboarding Mui Ne"** failed the on-category match and was dropped.
- Added `"kitesurf"` with the full kite synonym family.
- Added a **stem fallback**: when no exact key matches, union every family that
  shares a ≥4-char stem with an activity word (so `windsurf`, `paddleboard`, …
  also resolve). Tokens now:
  `('kite','kiteboard','kiteboarding','kitesurf','kitesurfing','kiting')`.

### 2. Yield — scope (`generate_tour_text.py`)
"**at Mui Ne beach**" geocodes to an ~11 m **hotel point** ("Mui ne Beach hotel",
bbox `[10.9547,10.9548,108.2412,108.2413]`), whose bbox excludes nearly every
school; "**Mui Ne**" geocodes to the **ward** (bbox `[10.909,11.028,108.185,108.350]`
≈ 13 × 16 km). Added `_widen_generic_feature_scope(scope, location)` and applied
it at both `_scope_from_request` returns: for a **business/activity-provider**
request it strips a trailing generic natural-feature word (beach/bay/dunes/lagoon/
cove/waterfront/seafront/shore/coast/strand) from the leading scope segment, so
`Mui Ne beach, Vietnam` → `Mui Ne, Vietnam`. A walking tour **on** the beach keeps
the beach (it is the subject). Live log confirms maps-first discovery ran in
`'Mui Ne, Vietnam'` and found **5 schools**.

### 2b. Yield — closure gate drop-on-non-evidence (`restaurant_practicals.py`)
With the wider scope, discovery found **5** real schools, but
`venue_still_operating` then dropped 3 of them (2/5 delivered) because the model
answered `still_operating: false` with reasons like *"No sources confirm it is
still operating under that exact name"* — **absence of confirmation, not closure
evidence**. The function's own docstring rule (D162) is that absence of evidence
must never delete a stop. Fix: when `still_operating` is `false` but there is **no
successor**, **no change date**, and the reason reads as a non-finding (*no
source / cannot confirm / no information / unknown / not found …*) **and** carries
**no closure word** (closed/shut/rebrand/replaced/no longer/permanently), treat it
as UNKNOWN → keep. This rescued Muine Kitesurf School, C2Sky, Palm Kite Club and
Mui Ne Bay Kite School → **5/5**. Genuine closures still drop:
`tests/test_d539_closure_regression.py` passes (Joël Robuchon, known-closed Le
Vistamar).

### 3. Gemini — route tier C through `RESEARCH_BACKEND` (`escalating_lookup.py`)
LOCAL-834 moved the per-stop practicals through `story_leads.research_with_sources`
(the one selector that honours `RESEARCH_BACKEND`). The remaining Gemini was the
provider-discovery ladder's **tier C** — a **direct** grounded-Gemini POST to
`generativelanguage.googleapis`, gated only by `allow_grounding`, the breaker and
the budget, never by the backend. Added `_tier_c_gemini_disallowed_by_backend()`
(True when `research_backend() != 'gemini'`), wired into `grounding_blocked` and
as defense-in-depth inside `_tier_c_gemini`. On the cheap/serper arm tier C is
skipped and discovery stays on tier B (Serper Places) — honest shortfall over a
billed Gemini top-up. On the default backend tier C is unchanged (router swap,
not a ban). Live: `gemini_grounding requests=0`, **$0 Gemini**.

### 4. Category label leak (`generate_tour_text.py`)
`'restaurant'` is the INTERNAL name of the places/business arm. For a non-food
tour it leaked to the title (`- Restaurant Tour`) and the machine header
(`Tour-Category: restaurant`, which the app surfaces as metadata + an icon). Added
`_places_arm_neutral_header(request, tour_category)` → returns `'places'` when the
category is `restaurant` **and** the request is not about food. Phase 6 now writes
a neutral machine category (`Tour-Category: places`) and labels the title with the
request's own activity words (**"Kitesurf"**); the three partial-tour (cost-ceiling)
headers are neutralised too. A genuine food request (seafood restaurants, cafés,
street food) keeps `restaurant`.

### 5. Fabrication gate for the places arm (`generate_tour_text.py`)
**Root cause:** the prose entity grounding gate (`apply_prose_entity_grounding_gate`)
and the no-invent story pass both run **only for `tour_category == 'museum'` with
an exhibition checklist**. The kite tour is the places arm (`'restaurant'`), so
**nothing** checked that a person named in its prose appears in the stop's source
material — an LLM-invented proprietor ("Duc") with a fabricated "fusion" claim
sailed through. Also, `extract_person_names` requires a **multi-word** name, so the
single-token "Duc" was invisible even to the museum gate.

Added **PHASE 5.158a2**, scoped to the places arm: per stop it builds a grounding
corpus from the retrieved material (name, address, `stop_corpus` passages,
research/evidence/why/examples/reviews) and runs (a) the museum primitives
(`extract_person_names` + `check_person_grounded` + `remove_person_from_text`) for
multi-word names, and (b) a conservative **single-token subject-action detector**
that drops a sentence whose first token is a capitalised non-filler name followed
by an action verb when that name is absent from the corpus and the stop name. No
corpus for a stop → skip (D162). Live, it dropped **"Their vision was to fuse
Dutch kitesurfing expertise with … Mui Ne's co…"** (the exact "fuse" shape) plus 9
other ungrounded person/org attributions; no false positives on ordinary prose
("Lessons run daily", "Visitors gather", "The school opened").

---

## Tests

`test_local843_activity_yield.py` — **19 tests, all pass**, built from the exact
ticket string:
- `YieldTokenFamily` (4): kitesurf → full kite family; 6 real schools are
  providers; off-category rejected; filter keeps schools, drops padding.
- `YieldScope` (4): beach scope widens to town; helper strips the feature;
  walking-ON-beach not widened; bare feature left alone.
- `GeminiRouting` (3): tier C disallowed on the cheap arm + direct returns `[]`;
  allowed on default; the ladder never resolves via tier C / never calls Gemini on
  the serper arm.
- `CategoryLabel` (4): kite/scuba/yoga/surfboard → `places`; food requests →
  `restaurant`; museum/walking untouched.
- `Fabrication` (5): ungrounded "Duc" flagged; grounded "Duc" kept; no false
  positives on ordinary prose; museum primitives available.

**Regression:** `tests/test_local835*`, `830`, `788b` (60 pass),
`test_local834_places_no_gemini` (4 pass), `test_local664` (9 pass),
`test_d539_closure_regression` (pass), scope/header `local591/634/286` (45 pass),
`tests/ -k "escalat or grounding or entity or 784 or 722"` → 128 pass. The only
failures (`test_local378` ×2, `test_local311` ×1) are **pre-existing on base
`d2ad4f74`** (verified via `git stash`) and unrelated to these changes.

---

## Files

**Modified (4):** `category_match_guard.py`, `generate_tour_text.py`,
`escalating_lookup.py`, `restaurant_practicals.py`
**New (2):** `test_local843_activity_yield.py`, `run_local843_live.py`

Committed with an explicit file list (never `git add -A`). No `DELETE`, no live-DB
writes, no shared-container access; no edits to DECISIONS.md / CLAUDE.md /
BACKLOG.md / WORK_QUEUE / `.continuous_dev/` / SUBSCRIBED_COMMUNICATION_01.MD /
`legal/` / GCLOUD_STORIED_START_HERE.md / TRAVEL_PROJECTS.md.
