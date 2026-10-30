# SUBMISSION — LOCAL-826

**Museum canonical-title verification drops famous works and accepts wrong ones; a false "N exhibitions on view" shortfall line**

Branch: `LOCAL-826-museum-canon` · Base: subscribed `b2972f65` (contains dad37e92)

---

## The three defects and their root causes

### Bug 1 — famous works present in SPARQL are DROPPED "no canonical title match"
Field evidence (1): Orsay, `[D1v2] DROPPED 'L'Origine du monde' — no canonical title match`, the same for `La Nuit étoilée` and `La Naissance de Vénus`.

These works ARE in the venue's SPARQL set (verified live against Q23402: `L'Origine du monde`, `Olympia`, `Starry Night Over the Rhône`/`La Nuit étoilée`, `The Birth of Venus`/`La Naissance de Vénus`, all present with both an English and a French label). The drop is **not** a collection-size cap or a P195/P276 gap for Orsay.

Root cause: `filter_corpus_titles`' cross-language dedup (`dedup_cross_language`) keeps **one** label per work (the preferred language, French for Orsay) and folds the English label OUT of the matchable set. `build_dynamic_aliases` maps every variant to the work's **English** label. So in `match_candidate_to_canonical`, Step-1 alias lookup resolved the candidate to the English label, the guard `if _resolved in canonical_titles` failed (it was folded out), and for a work whose EN and local labels share no content words (`Starry Night Over the Rhône` / `La Nuit étoilée`) the fuzzy fallback also failed — so the famous work was DROPPED although fully present.

Fix (`story_miner.py`):
- new helper `_alias_target_present_in_set` — when an alias target is absent from the matchable set, FOLLOW it to any co-label of the SAME work (another normalized variant that aliases to the same target) that IS present, and return that surviving title. A candidate in **either** language then matches the one surviving label.

Proven generically — Orsay (fr), Rijksmuseum (`The Night Watch`→`De Nachtwacht`, `The Milkmaid`→`melkmeisje`), and `The Railway`→`Le Chemin de fer`.

### Bug 2 — a wrong work is VERIFIED on a shared place name
Field evidence (2): `[D1v2] VERIFIED 'L'Église d'Auvers-sur-Oise' → canonical: 'Chaumes de Cordeville à Auvers-sur-Oise'` — a different Van Gogh painting, accepted on the toponym "Auvers-sur-Oise" alone.

Root cause: the fuzzy matcher scored on bidirectional word overlap; the shared place words `auvers`/`oise` pushed the score over the 0.5 threshold with no requirement that the **distinctive subject** (`église` vs `chaumes`/`cordeville`) match. A second contributor: `build_bilingual_map_from_sparql` positionally aligns EN/local labels and, on non-parallel titles, emits spurious cross-language word pairs (e.g. `auvers↔cordeville`) that further corrupt the overlap.

Fix (`story_miner.py`, `match_candidate_to_canonical`):
- **Distinctive-subject gate** — a fuzzy match must share at least one DISTINCTIVE word *directly* (same token or ≥5-char prefix, NOT via the noisy bilingual map). Document frequency across the canonical set classifies a word as COMMON when it appears in **3 or more** titles (absolute threshold — a place name like "Auvers" recurs across a Van Gogh series; a distinctive subject noun does not). Genuine cross-language matches resolve through the alias path (Bug 1), not this fuzzy gate, so it can safely demand same-language distinctive evidence.
- **Specificity gate** — a candidate that is a strict subset of a longer canonical carrying an extra distinctive SUBJECT word is a different, more-specific work (`Olympia` ≠ `Une moderne Olympia`). A medium/material/format/period qualifier (the LOCAL-34 bare-title enrichment appends these: `Olympia` → `Olympia (toile)`) is a DESCRIPTOR, not a subject, and is excluded from this test so a bare famous title still matches its own enriched form.

Proven: `L'Église d'Auvers-sur-Oise` ≠ `Chaumes de Cordeville à Auvers-sur-Oise`; `Olympia` ≠ `Une moderne Olympia`; `The Railway` → `Le Chemin de fer` (not `Le pont d'Argenteuil`); `Olympia` → `Olympia (toile)` still matches.

### Bug 3 — a false "N exhibitions on view" shortfall line
Field evidence (3): GCloud 494/495/496, `"<Museum> currently has 1 exhibition on view, so this tour has 1 stop rather than the 5 you asked for."` — the shortfall was our own dedupe (fixed in dad37e92), **not** the venue's on-view exhibition list.

Root cause: `build_shortfall_sentence(mode="museum")` always emitted the "N exhibitions on view" clause, and several callers passed our *delivered* count as `exhibitions_on_view`. Blaming the venue for a loss caused by our filters is a false factual claim about the venue.

Fix:
- `about_museum_stop.build_shortfall_sentence` gains `count_is_sourced: bool = True`. The default keeps every existing museum caller **byte-identical** (LOCAL-600/612 contract preserved). When `count_is_sourced=False` the museum mode emits the neutral honest line: `"We could confirm K stop(s) at <Venue>, so this tour has K stop(s) rather than the N you asked for."` — no "exhibitions on view", no route vocabulary.
- Callers pass `count_is_sourced` honestly: the site-first exhibition harvest (`_LAST_SITE_FIRST_COUNTS['exhibitions_on_view']`) is the venue's own on-view list → `True`; the overview path (a 1-stop overview is OUR choice) and the verified-works main-loop museum path (loss to our filters) → `False`.

---

## Live run (budget enforced)

`TASK_BUDGET_ID=LOCAL-826 TASK_BUDGET_USD=0.90`, cheap museum arm, `DISABLE_STOP_POOL=1`, own disposable containers + throwaway postgres (never a shared `audioura-*` container, never the live DB). Wrapper `run_local826_live.sh`, runner `run_local826_container.py`. Full log: `LOCAL826_LIVE_RUN.log`.

### Orsay Museum, Paris, France (5 stops delivered) — D1v2 lines
```
[D1v2] VERIFIED 'L'Origine du monde'  → canonical: 'L'Origine du monde'
[D1v2] VERIFIED 'La Nuit étoilée'      → canonical: 'La Nuit étoilée'
[D1v2] VERIFIED 'La Naissance de Vénus'→ canonical: 'La Naissance de Venus'
[D1v2] VERIFIED 'L'Église d'Auvers-sur-Oise' → canonical: 'L'Église d'Auvers-sur-Oise'
[D1v2] VERIFIED 'Le Déjeuner sur l'herbe'    → canonical: 'Le Dejeuner sur l'herbe'
[D1v2] VERIFIED 'Bal du moulin de la Galette'→ canonical: 'Bal du moulin de la Galette'
[D1v2] VERIFIED 'Un enterrement à Ornans'    → canonical: 'Un enterrement à Ornans'
[D1v2] VERIFIED 'Arrangement en gris et noir n°1' → canonical: 'La mère de l'artiste'
[D1v2] VERIFIED 'L'Absinthe'           → canonical: 'L'Absinthe'
[D1v2] DROPPED  'Olympia'              — no canonical title match   ← see note
```
- **Bug 1 FIXED**: `L'Origine du monde`, `La Nuit étoilée`, `La Naissance de Vénus` — all DROPPED in the field evidence — now VERIFY.
- **Bug 2 FIXED**: `L'Église d'Auvers-sur-Oise` now resolves to its OWN title, **not** `Chaumes de Cordeville à Auvers-sur-Oise`. The exact false-accept from evidence (2) is gone.

**Note on the one `DROPPED 'Olympia'` line (a NEW observation, not in the ticket):** the LOCAL-34 bare-title enrichment had renamed the canonical `Olympia` → `Olympia (toile)` in the matchable set, and an earlier version of the specificity gate treated the material word `toile` as a distinguishing subject. This was fixed AFTER the live run (descriptor-word exclusion + the absolute df cutoff). The fix is proven end-to-end against the **real** Orsay canonical set (the same data path the live run uses): candidate `Olympia` → `Olympia (toile)` matches, `Une moderne Olympia` → itself, Église-present matches itself, Église-absent correctly DROPS. A second live tour was **not** run because the meter already stood at $0.5771 and a second Orsay (~$0.29) would risk the $0.90 cap.

### Belvedere Palace, Vienna, Austria (0 stops) — unrelated blockers
Two issues, both outside this bug: (a) `resolve_venue('Belvedere Palace', 'Vienna')` resolves to the **palace** Q211818 (its P195/P276 holds the Austrian State Treaty, the chapel and exhibitions — not the Klimt collection, which belongs to the Österreichische Galerie), a venue-resolution concern; (b) the disposable postgres lacks the `stop_corpus` table (`relation "stop_corpus" does not exist`), a pre-existing throwaway-DB schema gap. Neither touches the canonical-verification defect.

---

## Honest scope notes (generality testing on Louvre / Rijksmuseum / Met)

The ticket asked to test Orsay, Louvre, Belvedere, Rijksmuseum and the Met.
- **Orsay (fr) & Rijksmuseum (nl)** — the cross-language fix is proven: famous works match from a candidate in either language.
- **Louvre** — `Liberty Leading the People` / `The Raft of the Medusa` are simply **not linked to Q19675 via P195/P276** in Wikidata (240 works total, unchanged even at LIMIT 1500 — not a cap). This is a Wikidata collection-membership completeness issue (works link to departmental sub-collections), outside the reported cross-language defect; chasing sub-collections per venue is a separate, cost/latency-sensitive change (the Met already times out).
- **The Met** — Q160236's WDQS query times out (known LOCAL-810); the fallback chain handles it.
- **Belvedere** — venue-resolution picks the palace, as above.

These are documented rather than papered over; the reported defect (works present in the set being dropped, and wrong works accepted) is fixed generally.

---

## Tests

New: `test_local826_canon_and_shortfall.py` — 13 tests built from the exact field strings (Bug 1 cross-language both directions; Bug 2 Église≠Chaumes, Olympia≠Une moderne Olympia, The Railway→Le Chemin de fer, Olympia→enriched form; Bug 3 sourced vs unsourced phrasing).

Full regression (matcher / museum / shortfall suites), all green:
```
test_local826_canon_and_shortfall  test_w4_matcher  test_local24_corpus_filter
test_local24_regression  test_local589_fill_the_count  test_contained_regression
tests/test_local791c_titles  tests/test_local791e  tests/test_local811_pool_museum_checks
tests/test_local813_pins_round3  tests/test_local818_district_refill
test_local802_relevance_and_dedupe  test_local823_multilingual_junk  test_local823_title_body_dup
tests/test_local600_order_and_shortfall  tests/test_local612_shortfall_everywhere
tests/test_local602_overview_shortfall  test_local617_work_first
test_local627_reproduction_and_titles  test_local751_exhibit_museum
test_local582_museum_overview  tests/test_local577_museum_refill  tests/test_local362_exhibition_scope
→ 343 passed
```
Pre-existing failure, NOT introduced here: `test_local589_canonical_set_chrome_free.py` already fails on the base commit `b2972f65` (verified by `git stash`).

---

## Files changed (source)
```
 about_museum_stop.py      |  16 ++++-
 generate_tour_text.py     |  25 +++++--
 stop_pool_orchestrator.py |  30 +++++++--
 story_miner.py            | 167 +++++++++++++++++++++++++++++++++++++++---
```
Plus tests/harness: `test_local826_canon_and_shortfall.py`, `run_local826_container.py`, `run_local826_live.sh`.

---

## meter_report (service LOCAL-826, since the live-run start)

```
LOCAL-826                           461       0.5771         667315          66470

BY MODEL
                               requests          usd      tokens_in     tokens_out
gemini-flash-latest                  60       0.2113          57055          16668
gpt-4.1-mini                         94       0.1521         509613          30997
(none)                              119       0.1290              0              0
gpt-4o                                5       0.0382           6801           2115
gpt-4.1                               5       0.0245           4844           1853
gpt-4o-mini                         176       0.0220          87065          14837
text-embedding-3-small                2       0.0000           1937              0

TOTAL   requests=461  usd=$0.5771  tokens_in=667315  tokens_out=66470
```
Under the $0.90 cap. Full output: `LOCAL826_METER_REPORT.txt`.
