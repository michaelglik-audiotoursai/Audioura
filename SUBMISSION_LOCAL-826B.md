# SUBMISSION — LOCAL-826B

**Branch:** `LOCAL-826B-museum-canon-cache`
**Base:** subscribed `292f4975` (contains 112480f3 / LOCAL-826). `git merge-base
--is-ancestor 292f4975 HEAD` → 0.

Two field defects, both diagnosed against the EXACT cached data copied read-only
from the live Mac DB and fixed at source, with a defense-in-depth delivery check
and a budget-enforced live run.

---

## Defect 1 — the LOCAL-826 museum-canon fix did nothing on the CACHED path

**Evidence (LEAD):** Orsay (tour 864), on a run that used
`[LOCAL-810] venue_works_cache HIT Q23402/fr (n=300)`, still produced the
pre-826 drops — `[D1v2] DROPPED 'L'Origine du monde' / 'Olympia' / 'La Nuit
étoilée' / 'La Naissance de Vénus'` — and the wrong accept
`VERIFIED 'L'Église d'Auvers-sur-Oise' → 'Chaumes de Cordeville à
Auvers-sur-Oise'`.

### Root cause (proven, not inferred)

I copied the real cached rows read-only from the live DB and ran the REAL matcher
against them (`repro_local826b.py`, `tests/fixtures/local826b/*.json`):

* The **`venue_corpus` row for Q23402** was written **2026-10-08 by an OLD miner**
  at `corpus_version = 7`. Its `canonical_titles_json` (211 titles) and
  `sparql_works_json` (102 works) **do not contain the famous works at all** —
  no "Olympia", no "L'Origine du monde", no "La Nuit étoilée"/"Starry Night", no
  "La Naissance de Vénus"/"Birth of Venus". It carries only
  `Chaumes de Cordeville à Auvers-sur-Oise`.
* On a cache HIT, `generate_tour_text.py` matches against **that stale snapshot**,
  so the famous works are absent from the matchable set — they DROP — and the
  stale alias/title set yields the Église→Chaumes wrong accept. **Reproduced
  exactly** (repro part A).
* The **refreshed `venue_works_cache` Q23402/fr** (written 2026-10-30, **300
  works**) HAS every famous work with distinct `label_en`/`label_local`. Rebuilt
  from it, the matchable set is 736 titles and the 826 matcher **VERIFIES all
  four** (incl. the cross-language alias follow La Nuit étoilée → Starry Night,
  La Naissance de Vénus → Birth of Venus) and resolves Église to **The Church at
  Auvers, NOT Chaumes** (repro part B).

So the matcher fix was correct; the matchable set it ran against was a stale
snapshot that never held the works. **Rebuilding aliases from the cached
`sparql_works_json` cannot help** — that 102-work snapshot does not contain the
works either.

### Fix — `venue_resolver.py`: `CORPUS_VERSION` 7 → 8

`cache_get` filters `WHERE corpus_version = %s`, so bumping the version makes
every pre-826 `venue_corpus` row a **cache MISS** (no `DELETE`, the LOCAL-583/593
mechanism). The miss forces a fresh rebuild that re-fetches works via
`fetch_venue_works` — now served from the **refreshed `venue_works_cache`** — and
`build_canonical_titles_from_works` re-admits the famous works, so the 826
matcher verifies them and keeps Église ≠ Chaumes. **Why a bump, not an alias
rebuild:** the alias build is already correct; the stale corpus simply lacks the
works, and only a refresh (from the richer works cache) brings them back.

### Live-path Olympia follow-up — `story_miner.py`

The live run exposed one remaining drop: `[LOCAL-34] Will enrich bare title at
stop-naming: 'Olympia' → 'Olympia (toile)'`. The enriched label is the only
surviving form of the work in the set, and the sibling "Une moderne Olympia"
blocked the fuzzy specificity gate, so the bare candidate "Olympia" dropped.
Fix: `_DESCRIPTOR_WORDS` promoted to module scope; `_alias_target_present_in_set`
now follows a resolved bare title (`Olympia`) to its own **descriptor-enriched**
canonical (`Olympia (toile)`) — a title that is the resolved title plus ONLY
medium/material/format/period words or a bare year — while a sibling with an
extra **subject** word (`Une moderne Olympia`) stays a distinct work. Proven
offline against the EXACT cached payload with the real enrichment: all four
famous works match, Église → The Church at Auvers, and "Une moderne Olympia" →
"A Modern Olympia" (not folded).

---

## Defect 2 — Rijksmuseum (tour 866) Stop 4: truncated title, dropped body, repeated number

**Evidence (LEAD):** `Stop 4: A Militiaman Holding a Berkemeyer, Known as the
'Merry Drinker' (Een schutter` — a truncated title with NO body — followed by a
SECOND `Stop 4:` for the Great Wave (should be Stop 5).

### Root cause (traced in the generator log, reproduced with the real guard)

From `gen_826_proofs.log`: all 5 stops narrated correctly (Stop 4 = Merry Drinker
350 words). Then the **LOCAL-628 stop editor** re-emitted Stop 3 with the Merry
Drinker's whole narrated body glued (headerless) after Stop 3's `Directions:`
line. `normalise_stop_headers` → `stop_dedup_collision_guard.dedupe_and_fix_stop_count`
**de-spliced** that orphan body — and **unconditionally DROPPED it**. The
de-splice assumed a headerless body after Directions is a duplicate preview of a
following stop (true for the w1/w4 cases it was built for), but here it was a
**unique, real, paid, narrated stop**. Deleting it left 4 stops; `[LOCAL-632]`
then restored a truncated `Stop 4:` header and the numbering collided.
Reproduced with the real guard in `repro_local826b_stop4.py`.

### Fix — `stop_dedup_collision_guard.py` (de-splice is now duplicate-aware)

`_desplice_segment` now returns the orphan tail instead of silently dropping it.
`dedupe_and_fix_stop_count` decides per orphan:
* `_orphan_duplicates_following()` — the orphan merely duplicates a FOLLOWING real
  stop (by the Directions hand-off title, or ≥ 0.6 narration token-overlap) →
  **DROP** (the w1/w4 behaviour, unchanged).
* otherwise, when the orphan carries a real narration body
  (`_orphan_has_narration_body`, a ≥ 80-char prose line that is not a distance
  preview) → **PROMOTE** it to its own `Stop N:` block, titled from the Directions
  hand-off, then renumber 1..k. A field-preview fragment (the tour-716
  `Type/Specialty:` glue) has no prose body and is still dropped.

### Delivery check — `tour_conclusion.py` + `generate_tour_text.py`

`check_stop_delivery(tour_text)` returns every structural defect: `DUPLICATE_NUMBER`
(same Stop N twice), `NON_SEQUENTIAL` (not 1..k), `EMPTY_BODY` (header with no
narration). Wired as the last museum-path step after the LOCAL-632 restore: it
logs violations, re-runs the LOCAL-801 dedupe/renumber guard to repair, logs any
unresolved defect, and rewrites the output file. On the real corrupt `tour866.txt`
it reports `DUPLICATE_NUMBER: Stop 4` and `NON_SEQUENTIAL: [1,2,3,4,4]`; it is
CLEAN on a well-formed tour.

---

## Tests — `test_local826b_cached_canon_and_stop4.py` (8, all pass)

Matcher on the EXACT cached Q23402 payloads: the stale `venue_corpus` snapshot
reproduces the drop + Chaumes wrong accept; the fresh `venue_works_cache` (300)
verifies the famous four and keeps Église ≠ Chaumes; Olympia matches its
LOCAL-34 enriched form while "Une moderne Olympia" stays distinct. Stop-4:
the corrupt `tour866.txt` fixture trips the delivery check; a unique lost-header
stop is promoted with its body + sequential numbering; a duplicate orphan is
still dropped (no regression); a clean tour has no violations.

**Regression:** 199 related tests pass (826, 801, 743, 632, 639, 24, W4, 403,
722, 623, 624, 642, 667, 634). All five edited modules compile.

---

## Live — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-826B TASK_BUDGET_USD=0.90`)

`run_local826b_live.sh` + `run_local826b_container.py`: own throwaway postgres
(project `local826b`, never a shared `audioura-*` container, never the live DB),
**seeded with the REAL cached rows** copied read-only from the live DB
(`tests/fixtures/local826b/seed_real_cached_rows.sql` — stale v7 `venue_corpus`
for Q23402 + Q190804, and the refreshed `venue_works_cache` 300/298/294). Cheap
museum arm, `DISABLE_STOP_POOL=1`, meter contract `METER_SERVICE=LOCAL-826B`.

Metered total **$0.8951 / $0.90** (two tours). Mechanism proven in the log:
`CORPUS_VERSION=8` → `venue_cache MISS for Q23402/Q190804` (stale v7 ignored) →
rebuild → `venue_works_cache HIT n=300` → `SPARQL source: 736 canonical titles`
→ `Injected 663 dynamic aliases`.

**Orsay — D1v2 lines:**
```
[D1v2] VERIFIED 'L'Origine du monde'      → 'L'Origine du monde'
[D1v2] VERIFIED 'La Nuit étoilée'         → 'La Nuit étoilée'
[D1v2] VERIFIED 'La Naissance de Vénus'   → 'La Naissance de Venus'
[D1v2] VERIFIED 'L'Église d'Auvers-sur-Oise' → 'L'église d'Auvers'   (NOT Chaumes — wrong-accept FIXED)
[D1v2] DROPPED 'Olympia'  — fixed post-run in story_miner.py, proven offline vs the real cached payload
```
Delivered Stop headers (unique, sequential, delivery check CLEAN):
`1 L'Origine du monde · 2 Le Déjeuner sur l'herbe · 3 Bal du moulin de la Galette ·
4 La Nuit étoilée · 5 L'Église d'Auvers-sur-Oise`.

**Rijks — Stop headers (unique, sequential, no truncation, delivery check CLEAN):**
`1 De grote golf bij Kanagawa · 2 De Nachtwacht · 3 Het melkmeisje ·
4 Het Joodse Bruidje · 5 Gezicht op huizen in Delft`.

The budget cap was effectively reached ($0.8951/$0.90); the Olympia matcher fix
landed after the run and is proven offline against the exact cached data rather
than re-run live, to honour the budget contract.

---

## Files changed
* `venue_resolver.py` — `CORPUS_VERSION` 7 → 8.
* `story_miner.py` — module-level `_DESCRIPTOR_WORDS`; alias-follow to a LOCAL-34
  descriptor-enriched canonical.
* `stop_dedup_collision_guard.py` — duplicate-aware de-splice that PROMOTES a
  unique lost-header stop instead of dropping it.
* `tour_conclusion.py` — `check_stop_delivery()`.
* `generate_tour_text.py` — wire the delivery check as the final museum-path guard.
* Tests/repros/harness: `test_local826b_cached_canon_and_stop4.py`,
  `repro_local826b.py`, `repro_local826b_stop4.py`, `run_local826b_container.py`,
  `run_local826b_live.sh`, `tests/fixtures/local826b/`.
