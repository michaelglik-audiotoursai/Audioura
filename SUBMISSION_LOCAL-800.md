# SUBMISSION — LOCAL-800: "What customers say" for business/place stops

**Base:** subscribed (`caa87604`) — `git merge-base --is-ancestor caa87604 HEAD` exits 0.
**Branch:** `LOCAL-800-customer-voice`

## Why
Michael on tour 469 (Russian, massage & spa near Ben Thanh Market): a day spa is
"acceptable with stories; not really interesting" — a spa rarely has history or a
famous visitor, so the story-first narration has little true to say. The
interesting, useful thing about a **business** is what its customers say: the
Google rating and how many left it, roughly what it costs, how long it has been
open, the treatments/dishes reviewers keep naming, the top praise and the one
recurring complaint.

## What this adds
For a PLACE-TYPE stop (dining and business/activity — the LOCAL-788B places path),
the narration now gets a short, **fully sourced** "What people say" paragraph, e.g.

> Visitors on Google give it 4.8 from about 840 reviews.

Built **only** from Serper Places data (reused — no extra cost where possible) and,
when needed, **at most one** extra Serper call per stop. Never invents a number, a
name or a quote; omits any item with no source; a complaint is surfaced only when
≥ 2 snippets agree; **no rating and no review count → no paragraph**. Translations
keep the numbers.

## Changes (6 files; never `git add -A`)

### New — `customer_voice.py`
The acquisition + composition module. Public API:
- `collect_facts(place_record, name, scope, allow_search=, api_key=, review_snippets=)`
  — reads rating / review count / price band / website / category off the Serper
  Places record the stop already carries (reuse, free). **The one allowed call:**
  when the stop has no rating yet, it makes a single `places_search` Places lookup
  (a 24 h cache hit — free — when the place was already fetched during generation;
  otherwise the one billable call) to GET the rating/count/price; when a rating is
  already in hand it instead makes one organic reviews search for the signature
  items / top praise / top complaint / "since <year>". **At most one extra Serper
  network call per stop, guaranteed.**
- `build_paragraph(facts)` — composes the paragraph from only sourced fields;
  returns `""` when no rating and no count.
- `customer_voice_prompt_block(facts)` — the prompt block handed to the narrator,
  with an explicit anti-invention rule ("Do NOT invent a rating, a review count, a
  price, a signature dish/treatment, a founding year or a quote…").
- `log_line(facts)` — the ticket's `[LOCAL-800] customer-voice <title> rating=… n=… items=…`.
- `facts_for_sources(facts)` — compact provenance stored with the stop's sources.

Hard rules in code: `_MIN_COMPLAINT_SNIPPETS = 2` (complaint needs ≥ 2 agreeing
snippets), `_MIN_ITEM_SNIPPETS = 2`, review counts rounded honestly ("about 840").

### `places_search.py`
`_normalize_serper_place` now preserves `_serper_rating_count`, `_serper_price_level`
and `_serper_website` (alongside the existing `_serper_rating`), so the
customer-voice fields survive onto every normalised Serper Places record and can be
reused with no extra call.

### `stop_existence_gate.py`
`business_replenish_candidates` and `dining_replenish_candidates` now carry the
`_serper_rating / _serper_rating_count / _serper_price_level / _serper_website /
_serper_category` fields from the Serper Places record onto each candidate dict, so
a maps-sourced stop arrives at the narrator already holding its customer-voice
numbers.

### `generate_tour_text.py`
- `_carry_customer_voice_fields(poi, cand)` helper + calls at the 6 maps-candidate
  append sites (places-first top-up, LOCAL-802 widening, empty-refill, business
  replenish, dining replenish, D545 places-first), so the `_serper_*` fields reach
  the poi dict.
- A `[LOCAL-800] CUSTOMER VOICE` acquisition pass (runs for `tour_category not in
  ('museum','facility')`, after the restaurant practicals block). Every stop of a
  restaurant/business/dining tour is treated as place-type; it calls
  `customer_voice.collect_facts`, attaches `poi['_customer_voice']`, stores the
  facts with the stop's sources, and emits the `[LOCAL-800]` log line.
  `LOCAL800_DISABLE_REVIEW_SEARCH=1` disables the extra call.
- The composed paragraph is injected into the per-stop prompt via
  `customer_voice.customer_voice_prompt_block(poi.get('_customer_voice'))` for
  `tour_category != 'museum'`, after the existing practicals/story blocks.

### New — `tests/test_local800_customer_voice.py` (33 tests, all pass)
Recorded Serper payloads (spa + café), fixtures only, no live web.

### New — `run_local800_container.py`
The isolated live-acceptance harness.

## Tests
```
python3 -m pytest tests/test_local800_customer_voice.py -q      # 33 passed
```
Covers: fields survive `_normalize_serper_place`; paragraph contains only sourced
facts, attributed; **no paragraph when rating/count missing**; **complaint only
with ≥ 2 agreeing snippets** (one grumble dropped); item only with ≥ 2 snippets; no
invented numbers; the `[LOCAL-800]` log line; **at most one Serper call** (Places
lookup when rating missing → reviews search skipped; reviews search when rating
reused → no Places lookup; none when disallowed or no key); prompt block + the
anti-invention rule + sources; and generator wiring markers.

### Regression
- 788B / 783 / 779B / 786 / 784 / 788_d545 / 791b / 779 place tests: **156 passed**.
- Full `tests/` suite on the branch **and** on the baseline (`git stash` to
  `caa87604`): the failure set is **identical** — 201 pre-existing,
  infrastructure-dependent failures (billing / wallet / newsletter / connectivity
  / DB), **zero new failures introduced** by this change.

## Live (OWN isolated container, `RESEARCH_BACKEND=serper`, Gemini OFF)
Image `audioura-tour-generator:latest`, network `local788b_default`, isolated
`local788b-postgres`. Gemini prepaid credit is depleted (LEAD note) so every tour
ran with `RESEARCH_BACKEND=serper` and no Gemini grounding.

**"coffee shops in Jamaica Plain, Boston" (3):** routes to the places path
(`category=restaurant`, `LOCAL-788B PLACES-FIRST`, stops Ula Cafe / Oda / J.P.
Licks). The LOCAL-800 pass **fired live**:
```
[LOCAL-800] customer-voice Ula Cafe rating=4.4 n=634 items=-
[LOCAL-800] customer-voice Oda rating=5 n=190 items=-
[LOCAL-800] customer-voice paragraphs attached to 2 place stop(s)
```
(the ratings/counts come from a single live Serper Places lookup per stop).

**Direct live demo against the raw Serper Places response** (each paragraph next to
the Serper data it came from; `allow_search=False` → **zero extra calls**, numbers
straight off the one Places response):
```
massage and spa @ Ben Thanh Market, Ho Chi Minh City
  Polished Salon, Spa, & Wellness  rating=4.8 count=835
    → "Visitors on Google give it 4.8 from about 840 reviews."
  LORLS SPA & MASSAGE  rating=None count=None  → (no paragraph — correct)
  Mary Massage & Spa Wellness  rating=None count=None  → (no paragraph — correct)

coffee shops @ Jamaica Plain, Boston
  Lê Phin         rating=4.7 count=500 price=$1–10
    → "Visitors on Google give it 4.7 from about 500 reviews; expect prices around $1–10."
  No Plates Coffee rating=4.9 count=542 price=$1–10
    → "Visitors on Google give it 4.9 from about 540 reviews; expect prices around $1–10."
  Caffe Paradiso   rating=4.4 count=865 price=$1–10
    → "Visitors on Google give it 4.4 from about 860 reviews; expect prices around $1–10."
```

**Cost (paid_api_calls, isolated DB, whole live session):** serper **$0.21**,
openai **$0.75**, gemini **$0.00**, **TOTAL $0.96 < $1.50 cap**. No live DB written;
every stored tour was an additive `is_test` row in the isolated container DB; no
`DELETE`.

## Known limitations (UNPROVEN, not caused by this change)
1. **Final delivery in the isolated container dies at PHASE 6** on `DATABASE
   UNREACHABLE — localhost:5433` (`tests/db_connection.py` hardcodes an auxiliary
   DB and ignores `DATABASE_URL`). The customer-voice pass runs at PHASE ~3.5,
   **before** this, so it is fully exercised and logged; only the fully-rendered
   tour text is not returned by the harness, and the harness `LiveRunMeter` showed
   `$0` because the crash preceded `meter.add_generation`. Actual spend is the
   `paid_api_calls` figure above. This is an environment issue, reported UNPROVEN.
2. The ticket's spa phrasing **"Massage and spa _near_ Ben Thanh Market"** routes
   to the WALKING path and scope-memory rejects the nearby spas (an upstream
   LOCAL-802 scoping issue, not this change). Customer-voice correctly only applies
   to place-type stops; the spa case is proven instead via the direct Serper Places
   demo above (Polished Salon 4.8/835).

## Process
Committed to `LOCAL-800-customer-voice` with explicit paths (never `git add -A`).
No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
TRAVEL_PROJECTS.md. No `DELETE`. Live DB never written.
