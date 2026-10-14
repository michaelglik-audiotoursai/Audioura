# SUBMISSION — LOCAL-584: Practical facts (currency + hours), one literal gate for every path

**Branch:** `LOCAL-584-practical-facts-currency`
**Base:** `storied` (1691f65) — `git merge-base --is-ancestor 1691f65 HEAD` exits 0.
**Agent:** Mac Mini Kiro

---

## Defect (Michael's tour 391 — Griffin Museum of Photography, Winchester MA, 2026-10-05)

Stop 1 said **`Museum Information: €12`**, and the log showed:

```
[LOCAL-91] Corpus fallback Museum Information: 08:00–20:00. €12
```

extracted from `https://griffinmuseum.org/about-the-griffin-2026/`. LEAD checked that
page (committed fixture `tests/fixtures/griffin_about_2026.html`): it says **`$12`**
(also `$8`, `$ 12.00`), has **no `€`**, and **no `08:00`** — its times are AM/PM
("Noon to 4 PM", "8 AM – 8 PM", "9 AM — 4 PM"). A listener acts on hours and prices;
this is the highest-harm kind of wrong fact.

Three root causes, confirmed by reproducing against the fixture on `storied`:
```
admission: '€12'                       # a $-only page, rewritten to €
hours:     [{'time': '08:00–20:00'}]   # "8 AM – 8 PM" synthesised to a 24h schedule not on the page
format_en: '08:00–20:00. €12'
```

1. **Currency.** `visitor_facts_extractor` hard-coded `f"€{amount}"` in *both* the FR and
   EN admission paths — the € default was applied regardless of what the page said.
2. **Hours.** `_normalize_time` blindly rewrote `8 PM` → `20:00`, so an AM/PM page became
   a 24h schedule whose tokens are nowhere on the page.
3. **Gate gap.** The **LOCAL-91 corpus fallback** wrote the extractor's `format_en()` string
   straight onto `Museum Information` with **no** verification — the one path that skipped
   the literal-token check LOCAL-582 added (`museum_overview._claim_tokens_in_source`).

---

## Fix

### 1. Currency is what the page says (`visitor_facts_extractor.py`)
- New `_format_price(symbol, amount)` renders a price using the currency **captured from
  the matched text** (leading symbol, trailing symbol, or ISO code). A bare number with no
  currency marker is emitted **without a symbol** — never a `€` guess.
- Both the FR (`Tarif/Entrée unique …`) and EN (`admission/ticket/Musée X …`) price regexes
  now capture the currency symbol/code (groups 1 or 3; amount group 2).
- `_has_price()` / `_ANY_PRICE_RE` make the scoring/merge logic currency-agnostic (so a `$`
  price is recognised as a price, not discarded for not being `€`).
- Result: Griffin `$12`, Musée Matisse `€12`, Palais Lascaris `€5`.

### 2. Hours as the page states them (`visitor_facts_extractor.py`)
- New `_normalize_time_sourced(raw, source_lower)`: a time is normalised to 24h **only if the
  24h token actually appears in the source** (`HH:MM` / `HHhMM` / `HHh` / the morning `H:MM`).
  Otherwise it keeps the **page-literal** form via `_page_literal_time` (`8 PM` → `8 PM`).
- Threaded through all four EN+FR hours call sites.
- Result: Griffin `8 AM–8 PM` (never `08:00–20:00`); genuinely 24h FR pages are unchanged —
  Palais `10:00–18:00`, Asian Arts `10:00–17:00` (their `10h`/`18h` tokens are on the page).

### 3. One gate for every path (`practical_facts_gate.py`, `generate_tour_text.py`, `museum_overview.py`)
- `practical_facts_gate` now owns the **single** literal check `claim_tokens_in_source()`
  (moved from `museum_overview`), extended with a **currency-symbol guard**: a `€` claim on a
  page with no `€` is rejected. `museum_overview._claim_tokens_in_source` delegates to it.
- New `gate_formatted_facts(formatted, source_text, source_url, log)` splits a `format_en()`
  string into its segments and keeps a segment **only if** it (a) classifies as a practical
  claim, (b) passes `verify_claim_against_source`, and (c) passes `claim_tokens_in_source`.
  Anything else is **dropped and logged**:
  `[LOCAL-584] dropped unsupported practical fact: …`. A bare-clock-range fallback
  (`_facts_segment_claim`) ensures a span like `8 AM–8 PM` is *verified*, not passed through.
- The **LOCAL-91 corpus fallback** in `generate_tour_text` now runs `format_en()` through
  `gate_formatted_facts` before writing `operational_details`; if nothing survives, the field
  is **omitted**. LOCAL-35/39 and the LOCAL-582 overview share the same check — one gate.

Belt-and-braces: even if the extractor ever regressed, the gate would still drop a `€` claim
on a `$` page, or a `20:00` not on the page.

---

## Tests — `test_local584_practical_facts_currency.py` (14 tests)

- **Griffin fixture** → admission keeps `$`, never `€`; formatted facts never contain `€`;
  hours never synthesise `08:00`/`20:00`; every token is on the page.
- **Shared gate** → old buggy `08:00–20:00. €12` is **fully dropped and logged** with the
  `[LOCAL-584]` prefix; corrected `8 AM–8 PM. $12` **survives whole**; a `€12` claim on the
  `$` page fails the literal check while `$12` passes.
- **French** (Matisse / Palais) → still `€12` / `€5`; Palais 24h hours kept; `€` facts survive
  the gate against a `€` source (no regression).

**RED on storied, GREEN after.** Checked out the `storied` versions of the two changed
modules and ran the new suite: **9 failed** (euro currency, `€` in formatted, `08:00/20:00`
hours synthesis, missing `gate_formatted_facts`/`claim_tokens_in_source`). After the fix:
**14 passed**. (The gate import is lazy so the extractor assertions fail with clear messages
on `storied` rather than erroring at collection.)

### Required suites kept green (paste exits)
```
test_local584_practical_facts_currency.py ....... 14 passed
test_local582_museum_overview.py .................. 20 passed
tests/test_local35_visitor_facts.py ............... 23 passed
tests/test_local36_practical_facts_qa.py .......... 26 passed
tests/test_local91_corpus_provenance.py ............ 8 passed
test_palais_fix_lead_fixture.py ................... 23/23 assertions hold
test_local38_theme_threads.py ..................... 12 passed, 0 failed
test_local38_integration.py ....................... 4 passed, 0 failed
test_local394_never_drop_a_stop.py ................. 6 tests OK
```
Out-of-scope note: the LOCAL-39 **beat** suite (`test_local393_*`) has 3 **pre-existing**
failures (person-name "Mourlot Frères", place-in-action). They import `story_beat_injector`,
which this branch never touches — `git diff storied..HEAD` is 5 files only
(`generate_tour_text.py`, `museum_overview.py`, `practical_facts_gate.py`,
`visitor_facts_extractor.py`, `test_local584_practical_facts_currency.py`, plus the two live
harnesses). They pre-exist on `storied` and are unrelated to practical facts.

---

## Live run in the container (D608, OpenAI hard cap $1.00)

Rebuilt the generator image from this worktree's **HEAD** (`71aaba5`) with
`Dockerfile.generator` and `--build-arg GIT_SHA=<HEAD>`; verified the fix is baked in
(`/app/.git_sha` matches; `gate_formatted_facts`, `_normalize_time_sourced`, `_format_price`
all present). Ran one-shot containers on the `development_default` network (DB `postgres-2`,
`gpt-4o`, `COST_HARD_LIMIT_USD=1.00`). **Never DELETE.**

**Griffin museum generation** (`run_local584_live.py`) — the official-site path omitted the
field safely, because the live site changed since the defect:
```
[LOCAL-39] No visitor info sourced — Museum Information field OMITTED
```
Today `griffinmuseum.org/plan-your-visit` and `/visit` publish hours but no price, so the
extractor omits (too short) — silence over a half-fact. The committed fixture is the ground
truth for the 2026-10-05 defect.

**Practical-facts path against the committed defect source** (`run_local584_griffin_facts.py`,
in the container, no LLM) — the exact LOCAL-35 extractor + LOCAL-91 corpus-fallback gate:
```
[fixture] raw extractor format_en(): '8 AM–8 PM. $12'
[fixture] Museum Information:         '8 AM–8 PM. $12'
[fixture] ✓ no € ; ✓ no 08:00/20:00 ; ✓ every token on the page
[fixture] gate dropped: []
```
And the old buggy string, fed to the same gate in the container, is fully rejected:
```
[LOCAL-584] dropped unsupported practical fact: '08:00–20:00' — not supported by source (gate)
[LOCAL-584] dropped unsupported practical fact: '€12' — distinctive token (price/day/currency/condition) absent from source
OLD BUGGY -> surviving: '' | dropped: ['08:00–20:00', '€12']
```

### `audio_tours` counts (never DELETE)
```
audio_tours BEFORE: 203
audio_tours AFTER : 203
```
`generate_tour_text` does not insert tour rows (only the orchestrator does); the harnesses
only COUNT. No DELETE was issued at any point.

---

## Files changed
```
visitor_facts_extractor.py                 currency-from-page + source-aware hours
practical_facts_gate.py                    the ONE literal gate (claim_tokens_in_source, gate_formatted_facts)
museum_overview.py                         _claim_tokens_in_source delegates to the shared gate
generate_tour_text.py                      LOCAL-91 corpus fallback routed through the gate
test_local584_practical_facts_currency.py  red-on-storied / green-after tests
run_local584_live.py                       live Griffin generation harness ($1 cap)
run_local584_griffin_facts.py              live/offline practical-facts proof (no LLM)
```

Process: did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
`.continuous_dev/STATUS.md`. Committed after each step.

---

## r2 — Hours belong to the venue, not a satellite gallery

**Base:** `LOCAL-584-practical-facts-currency` HEAD **37f6000** (`git merge-base
--is-ancestor 37f6000 HEAD` exits 0; `git rev-list --count 37f6000..HEAD` ≥ 1).

### Why r1 bounced (LEAD, 2026-10-05 13:3x)
The currency fix and the one-gate routing were right. But the hours r1 stated for the
Griffin Museum — **`8 AM–8 PM`** — are the **Lafayette City Center *satellite* gallery's**
hours. The museum opens **Tuesday–Sunday, Noon–4 PM** and is **closed Mondays**. A listener
told "8 AM–8 PM" arrives four hours before the museum opens. Faithful to a line, wrong for
the venue. The committed fixture `tests/fixtures/griffin_about_2026.html` lists, in order:

```
<h2>Hours</h2>        Tuesday through Sunday: Noon to 4 PM   Closed: Every Monday, Easter …
<em>Satellite Galleries</em>   Lafayette City Center Gallery  8 AM – 8 PM daily.
                               Jenks Center Gallery  Monday through Friday 9 AM — 4 PM
<h2>Admission</h2>    General Admission: $12 for adults  $8 for seniors …
footer: 67 Shore Road, Winchester, Ma 01890 … Hours: Tues-Sun Noon-4pm
```

The r1 extractor bound to the **first** time range it saw in the flattened page — the
satellite's "8 AM–8 PM" — and never captured the "Closed: Every Monday".

### Fix — bind to the venue's own section (`visitor_facts_extractor.py`)

Structural, not a keyword list of words like "satellite":

- **`_html_to_sectioned_text(html)`** flattens a page but inserts a section sentinel
  (`\x1e`) ahead of every heading-like element (`h1..h6`, and the emphasised sub-labels
  `strong`/`em`/`b`/`th`/`dt`/`summary`/`figcaption` that WordPress-style pages use as
  sub-headings). This preserves the document's heading/section structure, which a fully
  flattened string destroys. `_fetch_visitor_pages` now flattens this way.
- **`_scope_text_to_venue(text, venue_name, venue_address)`** walks the sections in order
  and keeps only those that belong to the venue. A section is a **foreign-place block**
  when its heading names a place that is *not* the venue — detected structurally by
  `_heading_names_other_place`: the heading is a proper place label (contains/ends in a
  **place word** — Gallery/Galleries, Center/Centre, Building, Museum, Annex, Pavilion,
  Wing, Hall, Site, Location, Branch, House) **and** it neither matches a venue-level
  section heading (Hours/Admission/Tickets/Location/…), nor shares a ≥4-char token with
  the venue name, nor carries the venue's street-number. "Satellite Galleries" matches via
  "Galleries"; "Lafayette City Center Gallery" via "Gallery" — the word *satellite* is
  never special-cased. Everything under a foreign heading is dropped until the next
  venue-level or venue-named heading re-opens the venue's content.
- On a page with **no sentinels** (a plain, single-venue string) scoping is a **no-op** —
  so French municipal pages (Matisse/Palais, which the tests pass as plain text) are
  unchanged.
- Closed-days from the **same block**: the EN closed-day regex now also reads
  `Closed: Every Monday` (colon + "Every", IGNORECASE). EN hours accept the page-literal
  words **Noon/Midnight** (`_page_literal_time` renders them; the simple EN hours regex
  matches them), so "Noon to 4 PM" is read as `Noon–4 PM`.
- `venue_name`/`venue_address` are threaded through `extract_visitor_facts_from_text`,
  `_extract_best_facts`, `fetch_visitor_info_structured`, and
  `fetch_visitor_info_with_provenance` (which strips sentinels from the provenance
  `source_text` so the gate's literal checks see clean prose). `generate_tour_text` passes
  `_museum_venue_name` on both the official-site and corpus-fallback calls.

### Fix — the one gate keeps the venue's Noon hours (`practical_facts_gate.py`)
Binding to the venue exposed a second bug: the shared gate **dropped `Noon–4 PM`** because
its hours classifier and `_verify_hours` only understood digit times — so the venue's real
hours would have been silently lost. `_facts_segment_claim` and `_verify_hours` now treat
the page-literal words **Noon/Midnight** as time tokens, verified against the source like
any other. `Closed on Monday. Noon–4 PM. $12` now survives the gate **whole**.

Result on the committed Griffin fixture (was `8 AM–8 PM. $12`):

```
Closed on Monday. Noon–4 PM. $12
```

never `8 AM`, never `9 AM`, never `08:00`/`20:00`, never `€`; every token on the page.

### Tests — `test_local584_venue_bound_hours.py` (10 tests)
- Griffin fixture (sectioned) → hours `Noon–4 PM` (asserts **no** `8 AM`, **no** `9 AM`,
  no `08:00`/`20:00`), closed `Monday`, admission `$12` (no `€`), every token on the page.
- The one gate keeps `Closed on Monday. Noon–4 PM. $12` whole (nothing dropped).
- Scoping is a **no-op** on a plain single-section page (keeps its only hours).

**RED on 37f6000, GREEN after.** Loading the base `visitor_facts_extractor` and running
the same fixture proves the defect: base yields `8 AM–8 PM. $12` with **no closed day**;
after r2 the extractor yields `Closed on Monday. Noon–4 PM. $12`. (On base the new test
module also fails to import, since `_html_to_sectioned_text` does not yet exist.) The r1
suite is unchanged — its Griffin assertions ("no €", "no 08:00/20:00", tokens-on-page) hold
for the venue-bound result too.

### Required suites kept green
```
test_local584_practical_facts_currency.py ........ 14 passed   (r1, unchanged)
test_local584_venue_bound_hours.py ................ 10 passed   (r2)
test_local582_museum_overview.py .................. 20 passed
tests/test_local35_visitor_facts.py ............... 23 passed
tests/test_local36_practical_facts_qa.py .......... 26 passed
tests/test_local91_corpus_provenance.py ............ 8 passed
test_palais_fix_lead_fixture.py ................... 23/23 assertions hold, exit 0
test_local38_theme_threads.py ..................... 12 passed
test_local38_integration.py ....................... 4 passed
test_local394_never_drop_a_stop.py ................. 6 passed
```
(100 passed in the combined pytest run; palais script exits 0.) French (Matisse €12 /
Palais €5, Palais 24h hours) is unchanged — scoping no-ops without sentinels.

### Live run in the container (D608, OpenAI hard cap $1.00)
Rebuilt the generator image from this worktree's **HEAD** (`b74183d`) with
`Dockerfile.generator` and `--build-arg GIT_SHA=<HEAD>`; verified the fix is baked in
(`/app/.git_sha` = b74183d; `_html_to_sectioned_text`, `_scope_text_to_venue`, and the
gate's Noon/Midnight handling all present). Ran one-shot containers on the
`development_default` network (DB `postgres-2`, `COST_HARD_LIMIT_USD=1.00`). **Never DELETE.**

**Practical-facts path against the committed defect source** (`run_local584_griffin_facts.py`,
in the container, no LLM) — the LOCAL-35 extractor (now venue-bound) + the LOCAL-91
corpus-fallback gate:
```
[fixture] venue-bound extractor format_en(): 'Closed on Monday. Noon–4 PM. $12'
[fixture] Museum Information:                 'Closed on Monday. Noon–4 PM. $12'
[fixture] ✓ venue-bound (no 8 AM / 9 AM satellite) ; ✓ no € ; ✓ no 08:00/20:00 ; ✓ every token on the page
[fixture] gate dropped: []
```

**Griffin museum generation** (`run_local584_live.py`, `gpt-4o`, one shot) — ran once at
**$0.4536** (< $1.00 cap), 0 network failures:
```
Total API cost: $0.4536 (41853 tokens)
RESULT after 327.8s
audio_tours BEFORE/AFTER: 203 / 203   (never DELETE)
MUSEUM INFORMATION LINE (poi 1): (no Museum Information line emitted)
```
As in r1, the live official-site path today lands on `griffinmuseum.org/plan-your-visit`
and `/visit`, which publish hours but **no price**, so the extractor omits (too short) —
silence over a half-fact. The committed fixture is the ground truth for the 2026-10-05
defect, and the container facts-path run (same baked HEAD) produces the exact venue-bound
Museum Information line above.

### Files changed (r2)
```
visitor_facts_extractor.py                 section the page by headings; read only the venue's block
practical_facts_gate.py                    gate keeps page-literal Noon/Midnight hours
generate_tour_text.py                      pass venue name on both visitor-info calls
test_local584_venue_bound_hours.py         venue-bound hours tests (red on 37f6000, green after)
run_local584_griffin_facts.py              harness updated: sectioned + venue-bound, asserts no satellite leak
```
Process: did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
`.continuous_dev/STATUS.md`. Committed + pushed after each step.
