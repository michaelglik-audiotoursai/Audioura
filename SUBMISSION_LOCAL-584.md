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
