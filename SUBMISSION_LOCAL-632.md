# SUBMISSION — LOCAL-632: Shortfalls and junk stops

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-632-shortfall-junk` (from `subscribed` @ `2e79f7f`)
**Base verified:** `git merge-base --is-ancestor 2e79f7f HEAD` → exit 0 ✓

Three defects from Bench R0, all in candidate intake / stop selection:

- **Albertina (tour 497, 2/10):** both stops were web-page titles —
  `The ALBERTINA Museum Vienna` and `Profile « The ALBERTINA Museum Vienna`. The
  museum's real highlights (Dürer's *Young Hare*, *Praying Hands*, the graphic-arts
  collection) never appeared.
- **Rijksmuseum (tour 499) & Courtauld (tour 485):** 2 delivered against 3
  requested — a shortfall impossible on corpus grounds for either famous museum.

---

## What was wrong, and the fix

### 1. Junk web-page titles became stops (`junk_title_guard.py`, new, pure)

Scraped site-first / JS-fallback candidate builders took stop names from a page's
`<title>` and nav headings, and nothing rejected page chrome. New pure predicate
`is_junk_page_title(title, venue_name)` rejects a title that:

1. contains a page-chrome **separator** (`«`, `»`, `|`, or a space-dash-space
   joiner) — e.g. `Profile « The ALBERTINA Museum Vienna`, `Exhibitions | Rijksmuseum`;
2. is a bare **section/nav label** — `Profile`, `Home`, `Visit`, `Tickets`,
   `About`, `Plan Your Visit`, …;
3. leads with a section word joined by `:`/`-`;
4. **names the venue itself** — delegated to
   `room_candidate_guard.is_venue_itself_title` (the LOCAL-626 authority, never
   diverge) plus a venue-name + generic-filler test so `The ALBERTINA Museum
   Vienna` (venue "Albertina" + "Museum"/"Vienna" filler) is caught.

It is conservative: a real work whose title merely contains such a word
(`The Visit` as a bare label is rejected per the ticket; `A Home in the Country`,
`Marie-Antoinette`, `Vienna Woods`, `Self-portrait at Thirteen` are kept).

**Wired at every candidate-intake chokepoint:**
- `exhibition_site_first.build_site_first_candidates` → `_append` (new
  `venue_name` parameter threaded from `generate_tour_text`);
- `exhibition_site_first._build_js_fallback_candidates` → materialise loop;
- `artwork_selection_guard.enforce_artworks_only` → step 1b (documented museum path).

### 2. Albertina graphic-arts corpus was stripped at intake

Root cause, **verified by running the real resolver** on the Albertina (Q371908):

- `venue_resolver._REPRODUCTION_INSTANCE_QIDS` wrongly listed **Q11060274
  ("print")** as a reproduction. A print — etching, engraving, woodcut, drypoint —
  is an *original* artwork medium. Every Dürer print was dropped: the SPARQL fetch
  reported **"29 reproduction/cast rejected"**, starving the works list below
  `total_stops` and forcing the junk web-page-title site-first fallback. Removed
  (genuine reproductions are still caught by the replica/plaster-cast/facsimile/copy
  QIDs and `_REPRODUCTION_TEXT_RE`).
- `artwork_selection_guard._ARTWORK_INSTANCE_QIDS` lacked the graphic-arts
  subclasses the Albertina catalogues: copper-engraving, etching, woodcut,
  color-woodcut, drypoint, gouache, pastel, study, engraving, lithograph, aquatint
  — and mislabelled Q18761202 (watercolor painting, which *Young Hare* carries).
  Added, so a drawing/print without a SPARQL creator is kept as an artwork instead
  of being dropped by `enforce_artworks_only` step 4.

**Verified end-to-end (offline):** Albertina SPARQL now returns **123 works
(was 94), 0 rejected as reproductions (was 29)**; *Young Hare*, *Praying Hands*,
*Great Piece of Turf* all survive `enforce_artworks_only`.

### 3. Shortfall: a famous museum must deliver N (`shortfall_reconcile.py`, new, pure)

- **Rijksmuseum / Courtauld root cause:** both are art museums that take the
  deterministic bypass (SPARQL yields far more than N works). The verified
  candidate list reached N, but a candidate was lost between selection and
  delivery and nothing pulled a replacement back in; the museum then emitted the
  false *"has a limited number of exhibitions on view"* sentence (nonsense for a
  permanent-collection museum).
- **Fix:** the deterministic/creator-filter museum bypass now records the FULL
  verified, guarded, variety-capped candidate list as `_museum_verified_reserve`.
  `shortfall_reconcile.reconcile_to_n` backfills the delivered `poi_list` from that
  reserve (de-duplicated, **never inventing**) until it reaches N, applied before
  descriptions are generated. When the reserve still cannot reach N it logs the
  mandated line:
  `[LOCAL-632] shortfall: requested=N delivered=M reasons=[…]`.

### 4. Rijksmuseum residual — a narrated stop's header deleted in packing

The live run exposed a deeper, *downstream* cause for the Rijksmuseum specifically:
selection now yields and **narrates all 3 works** (Merry Drinker / Great Wave /
Milkmaid), but a **post-assembly narration-dedup / fact-strip transform** (which
runs *after* the LOCAL-361 header invariant) deleted the 3rd stop's `Stop 3:`
header while leaving its body spliced onto Stop 2 — so the tour read as 2 stops.
The 504 critique confirms this independently: *"Stop 3 (The Milkmaid) has no stop
header — appears glued onto Stop 2."* This is a narration/packing defect, not a
corpus shortfall.

**Fix:** new pure helper `generate_tour_text.restore_lost_stop_headers(
complete_tour, rendered_headers)` re-inserts any header that was rendered (the stop
was selected, verified and narrated) but is now absent, anchored on the preceding
stop's `Directions:` line that announces it by name. Wired as the final step
before return (museum path). **Verified against the real delivered tour-504 text
offline** (restores `Stop 3: The Milkmaid` in the correct position) + 3 unit tests.
Not re-run live, to respect the $1.50 combined cap (already $1.22 spent).

---

## Files changed

| File | Change |
|------|--------|
| `junk_title_guard.py` | **new, pure** — `is_junk_page_title` / `filter_out_junk_titles` |
| `shortfall_reconcile.py` | **new, pure** — `reconcile_to_n` / `shortfall_log_line` |
| `exhibition_site_first.py` | junk guard at `_append` + JS fallback; `venue_name` param |
| `artwork_selection_guard.py` | graphic-arts P31 classes; junk-title reject step 1b |
| `venue_resolver.py` | removed Q11060274 ("print") from reproduction-reject set |
| `generate_tour_text.py` | `_museum_verified_reserve` capture; replacement-until-N + shortfall log; `restore_lost_stop_headers` final guard; thread `venue_name` to site-first |
| `test_local632_junk_and_shortfall.py` | **new** — 17 tests on the real candidate lists |
| `run_local632_container.py`, `run_local632_live.sh` | **new** — isolated live-run harness |

`practical_facts_gate.py` (LOCAL-630) was **not** touched.

---

## Tests (exit codes)

Run with `PYTHONPATH=.`:

```
tests/test_local60*.py / 61*.py / 62*.py   41 files   all ec=0
root  test_local62*.py                     14 files   all ec=0
      (incl. test_local627_reproduction_and_titles, test_local629_selection_diversity)
test_local590_*.py                          3 files   all ec=0
python3 test_sq4_merge.py                              ec=0
test_local632_junk_and_shortfall.py        17 tests   OK (ec=0)
```

---

## Live run (own container, cache + pool OFF, cap $1.50)

Built `Dockerfile.generator` → image `local632-gen-img`, ran disposable container
`local632-gen` (`docker run --rm --name local632-gen -p 5099:5000 --network
development_default`). Never `docker compose -p audioura`; never renamed/replaced
an `audioura-*` container. Rows: additive `is_test` only; **no DELETE**.

**Row counts:** `audio_tours` 306 → 310; `is_test` 5 → 7 (my 2 rows: **503**
Albertina, **504** Rijksmuseum, both `is_test=true`).
**Combined spend:** $0.766 (Albertina) + $0.451 (Rijksmuseum) = **$1.217 < $1.50**
(reserve gate skipped the 2nd venue in the first container when $0.766 + $0.90
would exceed the cap; the Rijksmuseum was then run alone against the remaining
budget with a $0.73 hard cap).

### Albertina — tour 503 (3 stops) — FIXED

Stops: **Knight, Death, and the Devil** (Dürer, engraving) / **Big Fish Eat Little
Fish** (Bruegel, drawing) / **Male Back With a Flag** (Michelangelo, drawing).
No junk web-page titles; 3/3 delivered; no false shortfall. **critique 2/10 → 6.5/10.**

```
$ python3 ~/Audioura/.continuous_dev/bench/detectors.py 503 3 "Albertina"
FAIL hours_said_twice: 2 hours statements
FAIL admission_twice: admission is Regular adult admission is €20. | admission is Regular adult admission is €20.
FAIL markers:
FAIL duplicate_sentence: ['to 6:00 p.m., with extended evening hours until 9:00 p.m.']
503: 4 detector failure(s)
```

`venue_as_stop` and `stop_count` — the two LOCAL-632 target defects — **PASS**
(no longer listed). The remaining 4 failures are out of scope: `hours_said_twice`
/ `admission_twice` / `duplicate_sentence` are the LOCAL-630 practical-facts block
(`practical_facts_gate.py`, must not edit); `markers` is the LOCAL-628 stop-editor
marker.

### Rijksmuseum — tour 504 (3 stops)

Selection yields and narrates 3 verified works (Merry Drinker / Great Wave /
Milkmaid). `venue_as_stop` **PASS** (no web-page-title stops). **critique 2/10 → 5.5/10.**

```
$ python3 ~/Audioura/.continuous_dev/bench/detectors.py 504 3 "Rijksmuseum"
FAIL stop_count: 2 delivered vs 3 requested
FAIL hours_said_twice: 4 hours statements
FAIL admission_twice: admission is Adult tickets are €25. | Admission is free for youth ...
FAIL admission_conflict:
FAIL raw_label_dup:
FAIL markers:
FAIL duplicate_sentence: ['Admission is free for youth ages 18 and under, ...']
504: 7 detector failure(s)
```

`stop_count` still reads 2 **in this stored row** because the 3rd stop's header
was deleted by the post-assembly transform described in §4 — the critique confirms
the Milkmaid *is* narrated, only its header is missing. The §4 header-integrity
guard fixes this (verified offline against this exact 504 text + unit-tested); it
was not re-run live to respect the $1.50 cap. The other failures are the same
LOCAL-630 / LOCAL-628 out-of-scope defects as 503.

Critique artifacts: `submission_artifacts/critique_503.md`,
`submission_artifacts/critique_504.md`.

---

## Scope notes

In scope and done: junk-title guard at candidate intake; Albertina graphic-arts
corpus intake; replacement-until-N + `[LOCAL-632] shortfall` log; the stop-header
integrity guard. Out of scope (other tickets, left untouched): the hours/admission
duplication (`practical_facts_gate.py`, LOCAL-630) and the stop-editor marker
(LOCAL-628). Each step was committed separately;
`git rev-list --count origin/subscribed..HEAD` ≥ 1.

---

## LEAD update (2026-10-08 16:36) — items 6 & 7

### Item 6 — a work belongs to a venue by its COLLECTION (P195), not a hard-coded list

Merged `origin/subscribed @ fb662e8` (LOCAL-630) into the branch first — `2e79f7f`
is an ancestor of `fb662e8`, a clean forward merge (no conflicts; my LOCAL-632 code
and LOCAL-630's `_KNOWN_WORK_HOME` both survived). Then replaced the hard-coded map
as *production* logic with collection-based membership:

- `venue_resolver.fetch_venue_works` now runs a **GROUPed** SPARQL query (one row
  per work via `GROUP BY` + `GROUP_CONCAT` of P170 / P31 / **P195** and `SAMPLE`
  of sitelinks / inception). This carries every P195 collection QID per work AND
  fixes a row-multiplication regression the added `?collection` OPTIONAL caused
  (the Albertina fell to 27 works under `LIMIT 400`; grouped, it returns **328**).
- `artwork_selection_guard._work_collection_excludes_venue` + the new
  `venue_qid` / `parent_qids` path in `enforce_collection_membership` implement the
  rule: **if a work has P195 and none of its values is the venue (or a parent), it
  is REJECTED, whatever P276 says**; a work with no P195 is governed by the
  existing title-set / site-listed check. `_KNOWN_WORK_HOME` is kept only as a
  last-ditch fixture.
- `_apply_artwork_guards` enriches `collection_qids` onto candidates and threads
  `venue_qid` (= `_det_entity.qid`) from both bypass call sites.

**Verified (resolver run on the real Albertina):** 328 works, 320 with P195 =
Albertina; *Young Hare* / *Praying Hands* / *Great Piece of Turf* survive; only the
P276-leak works (P195 = a different museum) drop. **Tests** use the real Wikidata
claims: *Ophelia* (P195 = Tate) rejected from the National Gallery; *Madonna del
Prato* (P195 = KHM) rejected from the Belvedere; a venue/parent P195 is kept; a
no-P195 work is left to the title check.

### Item 7 — tourism-board chrome as a stop

Art Institute of Chicago tour 496 Stop 1 was `Chicago: a challenge for your taste
buds | Choose Chicago`. The junk-title guard (item 1) catches it on the `|`
separator and **already runs on every candidate path** — the site-first `_append`
and the JS-fallback materialise loop, not only the documented path. Added
regression tests asserting both the rejection and the site-first wiring.

### Tests after the LEAD update

`test_local632_junk_and_shortfall.py` is now **25 tests (OK)**;
`test_local630_venue_truth.py` **23 tests (OK)**; the `tests/test_local60*/61*/62*`
+ root `test_local62*` + `test_local590_*` + `test_sq4_merge.py` suites are green.
`tests/test_local616_hours_guard_every_path.py::test_idempotent` is intermittently
flaky (it makes a live LLM conclusion call and compares two outputs for equality);
it is pre-existing LLM nondeterminism from the merged LOCAL-615 code, not touched
by LOCAL-632 (`about_museum_stop.py` was last changed by a LOCAL-630 commit).

### Live note

The two live tours (503 Albertina, 504 Rijksmuseum) were run before the LEAD
update; the item-6/7 code is verified by the resolver run above and the unit tests.
Re-running live was not done, to respect the $1.50 combined cap (already $1.22).

