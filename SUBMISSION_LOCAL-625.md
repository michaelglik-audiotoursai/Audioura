# SUBMISSION — LOCAL-625: Practical facts and stop selection on new venues

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-625-facts-and-selection` (from `subscribed` @ `a674cde`)
**Base:** subscribed — `git merge-base --is-ancestor a674cde HEAD` exits 0.

Four defects seen on LOCAL-623's fresh tours (Alte Pinakothek 471, SMK 470,
Unterlinden 469) are fixed, each with a regression test built on the real inputs.
The regression suite is green and both ticket venues were generated live in a
disposable container.

---

## The four fixes

### 1. Garbage hours — `10:00–18:00` became `00–18`
**Root cause.** `visitor_facts_extractor` extracted time ranges with the regex
`\d{1,2}h?\d{0,2}`. On a European dot/colon clock (`10.00` / `10:00`) that pattern
can match the *minute half* (`00`) instead of the whole clock, so `10.00-18.00`
yielded `("00","18")` → `"00–18"`. The Alte Pinakothek (Munich) page renders its
hours with a dot, so the tour spoke `Museum Information: 00–18; 00–20; 00–17; 00–19`.
A secondary bug: `practical_facts_gate._parse_info_text_into_claims` split a Museum
Information line on `[.;]`, breaking a dotted clock into `10`, `00-18`, `00`.

**Fix** (`visitor_facts_extractor.py`, `practical_facts_gate.py`):
- A bounded clock token
  `_CLOCK_TOKEN = (?<![\d:h.])\d{1,2}(?:[:.]\d{2}|h\d{2}|h)?(?:\s?(?:am|pm))?(?![\d:.]|h\d)`
  that matches a WHOLE clock and can never start on a minute fragment; used in
  both French-path hour regexes.
- `_normalize_time` now understands dot clocks (`10.00`→`10:00`) and a bare hour
  (`18`→`18:00`).
- The gate's sentence split no longer breaks inside a dotted clock.

**Verified:** `'10.00-18.00'` → `('10.00','18.00')`; `'10h à 17h'` → `('10h','17h')`;
`'10:00-18:00'` → `('10:00','18:00')`. On the base the same input produced
`['00–20','00–18']`. Live Alte Pinakothek now speaks `Museum Information: 10.00–18.00`
(the page's real hours), never `00–18`.

### 2. Wrong / inconsistent address — a per-work donor address shipped
**Root cause.** For a contained museum, `venue_bound_address` keeps a stop's own
address only when the stop's page supports it; but `_address_supported_by_page`
accepted *any* street address appearing anywhere on the page. SMK Stop 1's body
about *In a Roman Osteria* mentioned the donor-merchant's Copenhagen address, so
that per-work address shipped as the stop's Address while the other stop correctly
used the museum's address.

**Fix** (`about_museum_stop.py`): a stop address is kept only when the page
introduces it with a LOCATION cue (`located at` / `address` / `gallery` /
`entrance` / `housed at` …) within ~60 characters before it. A donor/merchant
address in a provenance sentence is rejected and the stop binds to the sourced
`venue_address` (Wikidata entity + the venue's own `/visit` page).

**Verified:** a donor address in prose binds to the museum address; a genuine
satellite introduced by "located at …" is kept. Live: both Mauritshuis stops
carry `Plein 29, Den Haag`; both Alte Pinakothek stops carry `Barer Str. 27,
80333 München`.

### 3. A room as a stop — "Obergeschoss, Kabinett 1-2"
**Root cause.** Two paths put a ROOM where an artwork belongs: (a) the site-first
builder's LOCAL-599B "named spaces" fill emits galleries/floors/the building as
stops; (b) the deterministic documented-works fill drew canonical titles straight
from the Alte Pinakothek's Wikidata catalogue, which stores its "Kabinett 1-23"
and "Saal …" rooms as *works*.

**Fix** (`room_candidate_guard.py` — new; wired into `exhibition_site_first.py`,
`stop_pool_assembly.py`, `venue_resolver.py`, `generate_tour_text.py`):
`is_room_or_space_title()` recognises a room / gallery / wing / floor / building
name in English, German and French (incl. `Kabinett`, `Saal`, `Raum`,
`Obergeschoss`) in three ways — the whole stripped head is a space designation;
a numbered space at the tail after qualifier words (`AP OG Kabinett 5`); or a
`<space-noun> <number>` unit anywhere (`AP OG -> Kabinett 4`). It keeps paintings
whose title merely mentions a room (`The Music Room`, `View of the Great Hall`).
It is applied:
- in the site-first builder (`_append` drops room candidates; the LOCAL-599B space
  fill is now behind `ALLOW_MUSEUM_SPACE_STOPS`),
- at the central canonical-title chokepoint in `generate_tour_text` (covers the
  fresh build AND the 30-day venue_cache HIT),
- at `build_canonical_titles_from_works` (source),
- as a last-line drop in `stop_pool_assembly.assemble`.
The shortfall is filled from the corpus / honest short count — never a room.

**Verified:** 0 false positives on 19 real works (incl. `Marshall 3`, `City Hall`,
`Composition II`, `Number 5`); catches every Kabinett/Saal/Room/Gallery-number
alias form. Live Alte Pinakothek canonical SET: `221 → 170`, dropping all
Kabinett/Saal entries. (See the residual note below.)

### 4. Wrong Wikidata entity — Mauritshuis resolved to a 0-work painting
**Root cause.** `city="The Hague"` is extracted from `"Mauritshuis, The Hague"`.
The city-qualified search `"Mauritshuis in The Hague"` matches ONLY a *painting*
titled exactly that (`Q17324051`, P31 = painting, 0 works, 0 sitelinks); the
search loop broke on that first hit and never ran the bare `"Mauritshuis"` query
that returns the real museum `Q221092` (national art museum, 111 works, 5
sitelinks) first. With no museum-typed candidate, Step 2 fell back to
`candidates[:5]` = the painting, and the tour clean-failed.

**Fix** (`venue_resolver.py`): (a) UNION the city-qualified and bare-variant hits
(de-duplicated by QID) instead of breaking on the first hit, so the museum stays
in the candidate set; (b) harden the no-museum-type fallback to rank candidates by
`(work_count, sitelinks)` and prefer any candidate with a collection over a 0-work
entity.

**Verified:** `resolve_venue('Mauritshuis, The Hague')` → `Q221092` (mauritshuis.nl).
Live Mauritshuis now generates (the base clean-failed).

---

## Tests (item 5)

`test_local625_facts_and_selection.py` — one test per defect, on the real inputs:
hours parse, address, room-as-stop, venue-entity ranking (7 cases, all pass).
Items 1, 2 and 4 were confirmed to FAIL on the `a674cde` base and pass with the
fix (item 1 base = `['00–20','00–18']`; item 2 base keeps the donor `14 Bredgade
Street`).

## Regression suite (item 6) — all exit 0

```
test_local590_assembly.py                 exit=0   16 passed
test_local590_orchestrator.py             exit=0    8 passed
test_local590_pool_store.py               exit=0   18 passed
test_local605_tour_coordinates.py         exit=0   17 passed
test_local607_pooled_coherence.py         exit=0   21 passed
test_local617_work_first.py               exit=0   47 passed
test_local618_grammar_splice_lint.py      exit=0   10 passed
test_local618_orientation_pretell.py      exit=0    7 passed
test_local618_subentity_venue.py          exit=0    8 passed
test_local618_unpublished_hours.py        exit=0    8 passed
test_local620_story_types_prefs.py        exit=0   27 passed
test_local623_stop_body_defects.py        exit=0   16 passed
test_local625_facts_and_selection.py      exit=0    7 passed
tests/test_local600_order_and_shortfall   exit=0   24 passed
tests/test_local602_* (11 files)          exit=0   all passed
tests/test_local603_meter_and_l2.py       exit=0    5 passed
tests/test_local603_preflight.py          exit=0    9 passed
tests/test_local604_plan.py               exit=0   21 passed (needs Postgres :5433; 21 DB setup-errors when the dev DB is down — environmental, not a regression; this branch does not touch plan code)
tests/test_local606_replace_on_change.py  exit=0    5 passed
tests/test_local609_cost_breakdown.py     exit=0   18 passed
tests/test_local60_cost_metering.py       exit=0    8 passed
tests/test_local611_canary.py             exit=0    7 passed
tests/test_local612_shortfall_everywhere  exit=0   21 passed
tests/test_local613_meter_and_cap.py      exit=0   14 passed
tests/test_local614_* (5 files)           exit=0   all passed
tests/test_local615_* (4 files)           exit=0   all passed
tests/test_local616_* (5 files)           exit=0   all passed
tests/test_local619_real_conclusion.py    exit=0   21 passed
tests/test_local622_lookup_budget.py      exit=0   21 passed
python3 test_sq4_merge.py                 exit=0   ALL TESTS PASSED
```
No new failures were introduced. (Pre-existing, network-dependent failures that
are identical on the base — `test_local592_r4_dayrange_spoken`,
`tests/test_local359_scope_check_address` — are untouched by this branch and are
not in the required suite.)

## Live runs (item 7)

Own disposable container `local625-gen` (`docker run --rm`, compose-free) on
`development_default`, tour cache OFF (`DISABLE_TOUR_CACHE=1`), hard cap
`COST_HARD_LIMIT_USD=1.00` + `TEST_GEMINI_MAX_USD=1.00` combined, metered by
`tests/live_run_meter.py`. Rows are **additive is_test only**; **no DELETE**.

**FRESH re-run (final, supersedes the earlier blocked note below).** Both venues
regenerated fresh in one capped run after the external billing condition cleared.
`audio_tours` row count: **490 before → 492 after** (total); is_test **420 → 422**.
Combined live-run meter TOTAL **$0.4725** (openai $0.3695, gemini_grounding
$0.0700, gemini_tokens $0.0120, serper $0.0210, preflight $0.0592) — under the
$1.00 cap. New rows: **id 702 (Mauritshuis), id 703 (Alte Pinakothek)**, both
`is_test=t`.

**Mauritshuis, The Hague** (id 702) — all four fixes clean:
```
[venue_resolver] Candidates: ['Q17324051','Q221092','Q1942873', ...]  # 0-work painting is FIRST
[venue_resolver] Resolved: 'Mauritshuis' → Q221092 (Mauritshuis)      # item 4 — ranked past the painting
[venue_resolver] SPARQL: 123 works found for Q221092                  # item 4 — real museum (base clean-failed)
Stop 1: Portret van Anna Wake (1605-voor 1669)                        # item 3 — a painting
Stop 2: Het loflied van Simeon                                        # item 3 — a painting
Address: Plein 29, 2511 CS Den Haag, Netherlands                      # item 2 — identical on both stops
Museum Information: Monday, 13:00–18:00. €21                           # item 1 — clean clock + admission
garbage-hours probe: CLEAN                                            # item 1
```

**Alte Pinakothek, Munich** (id 703) — all four fixes clean; **residual RESOLVED**:
```
Museum Information: 10.00–18.00                                        # item 1 — no "00–18"
garbage-hours probe: CLEAN                                            # item 1
Stop 1: The Holy Family                                              # item 3 — a painting (Raphael)
Stop 2: Allegorische Frauengestalt mit Spiegel                        # item 3 — a painting (Baldung); NO Kabinett
Address: Alte Pinakothek, Barer Str. 27, 80333 München, Germany       # item 2 — identical on both stops
```
The prior residual ("AP OG -> Kabinett 4" on the earlier id 483) is **gone** in
this fresh build with the follow-up `_SPACE_UNIT_RE` fix in the image: both stops
are paintings.

**critique.sh** (listener review of the spoken text; files `critique_702.md`,
`critique_703.md` under `.continuous_dev/calib/critique/`):
- **Mauritshuis (702): 4/10.** None of the flagged defects are LOCAL-625 items —
  they are out-of-scope: a Rembrandt↔de Gelder same-title attribution bleed on
  Stop 2, a hallucinated "sackbut" cross-reference, and catalog-dimension filler.
  Item 4 cleared the clean-fail (the tour now generates).
- **Alte Pinakothek (703): 6/10.** None of the flagged defects are LOCAL-625 items
  — out-of-scope: an "oil on canvas" vs panel medium error, a dangling template
  bind ("acquisition by reflects …"), institutional filler. The original evidence
  tour 471 scored 2/10 with the garbage hours + room-as-stop; those are gone.

In both critiques the four LOCAL-625 defects are **absent**: no garbage hours (both
CLEAN), no wrong/inconsistent address (one museum address per stop), no room/
gallery/building stop (all four stops are paintings), and Mauritshuis resolves and
generates. The residual scores reflect pre-existing out-of-scope defects owned by
other tickets.

### Earlier blocked attempt (historical, now superseded)
An earlier attempt generated Alte Pinakothek (id 483) BEFORE the `_SPACE_UNIT_RE`
follow-up and shipped Stop 2 as "AP OG -> Kabinett 4"; a subsequent re-run was
blocked by a transient Gemini 402 (prepaid balance). That condition has since
cleared (verified by a 1-token probe returning HTTP 200), and the FRESH re-run
above (id 703) reconfirms the fix end-to-end. The guard is also covered by unit
test (`test_local625` + `is_room_or_space_title('AP OG -> Kabinett 4') == True`,
0 false positives on 19 real works).

## Files changed
```
about_museum_stop.py          # item 2
exhibition_site_first.py      # item 3 wiring
generate_tour_text.py         # item 3 canonical-SET chokepoint
practical_facts_gate.py       # item 1 split
room_candidate_guard.py       # item 3 (new module)
stop_pool_assembly.py         # item 3 last-line drop
venue_resolver.py             # item 3 source filter + item 4 ranking
visitor_facts_extractor.py    # item 1 clock token + normalize
test_local625_facts_and_selection.py   # item 5
run_local625_live.sh, run_local625_container.py  # item 7 harness
```

Did NOT touch `unglossed_reference_gate.py` (LOCAL-624 owns it).
Did NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
.continuous_dev/STATUS.md.
