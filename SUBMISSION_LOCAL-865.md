# LOCAL-865 — Palais Lascaris (Nice) delivers 1 of 6: "27 R4 candidates failed canonical match"

Branch `LOCAL-865-lascaris-canon`, base 806ee7b9 (`git merge-base --is-ancestor 806ee7b9 HEAD` → 0).

## 1. Trace (measured with `run_local865_diag.py` + the live run, not guessed)

| Candidate cause | Verdict | Evidence |
|---|---|---|
| venue canon empty / sparse | **Partly.** Wikidata holds 1 work, but the canon is 10 titles | `[D1v2] Canonical titles union: 10 site/wiki + 1 SPARQL = 11 total`; titles = "Raquel" + 9 instruments from fr-Wikipedia ("Harpe by Naderman (Paris, 1780)", …) |
| title-normalisation mismatch | **Yes, for the instruments.** R4 proposes bare "Harpe", "Basse de violon", "Guitar"; each is a strict subset of a longer canon title carrying extra distinctive words, which the LOCAL-826 specificity gate rejects | `story_miner.py` `match_candidate_to_canonical` (the `_cand_set < _canon_set` / `_extra` check, ≈ l.2960–2975); live log `[R4] dropped 'Harpe'`, `'Basse de violon'`, … |
| wrong "Lascaris" | **No.** Resolver picks Q34653010, coords 43.6977,7.2773, URL nice.fr palais-lascaris | `[venue_resolver] Resolved: 'Palais Lascaris' → Q34653010` |
| *why nothing rescued it* | tier is **`exhibit_museum`** (10 canon titles > 1 SPARQL) and both rescue blocks — thin-source verify (`generate_tour_text.py` ~l.16080) and building/area fallback (~l.16231) — are gated on `_verification_tier == 'thin'`, so they never ran | `[D1v2] 1/6 works verified — tier: exhibit_museum` |
| R4 asks only for paintings | R4 prompt (≈ l.16030): "INDIVIDUAL ARTWORKS … (painting, mosaic, sculpture, stained glass)" for a venue whose signature collection is ~500 instruments | live log round 2 candidates ("Tapestry depicting a Hunting Scene", "Virgin and Child with Saints …") |
| tour lat/lng offset | Tour coords = `first_poi_coordinates`, i.e. Stop 1's model coordinate, extracted *before* [D4]; [D4]'s "venue pin" only knew a hard-coded chagall/matisse table, else a corpus regex, else that same model point; and the returned tuple was never updated after D4 | LOCAL-861 `t1331`: `Coordinates: 43.707306, 7.305403` (2.5 km from the 43.6977,7.2773 P625 pin) |

## 2. Fix
- **`palace_museum_stops.py` (new)**: for a palace/historic-house museum, documented ROOMS and FEATURES become stops — instrument collection, frescoed ceilings, grand staircase, apothecary, chapel, state rooms/noble floor, façade/entrance, tapestries & furnishings. A feature ships only if a page *about this venue* (nice.fr / fr+en Wikipedia — already fetched for the resolved venue) names it in a sentence; the sentence is stored as `_feature_sources`/`_feature_facts`, and narration is instructed to use only those facts. A page that does not mention the venue can never ground a stop (D756). Nothing in the vocabulary is shipped unless the corpus names it: **the 17th-c. apothecary is NOT delivered for Lascaris because none of its fetched pages mention one** ("Pharmacies de garde" on nice.fr is site chrome and is deliberately not matched).
- **`generate_tour_text.py`**: (a) new block before UNIFIED-FILL, run for `thin` *and* `exhibit_museum` tiers; (b) R4 prompt widened to "OBJECT on display at THIS venue (artwork, musical instrument, tapestry, furniture)" for palace museums only; (c) [D4] now prefers curated pin → resolver Wikidata P625 → corpus → Stop 1, and sets the returned `first_poi_coordinates` to that pin; (d) feature stops get a sourced-facts-only narration instruction.
- Not changed: the LOCAL-826 specificity gate itself (it prevents real false accepts); the bare-instrument candidates are still dropped by it — the features fill the tour instead.

## 3. Tests (`tests/test_local865_palace_museum.py`, 13 pass)
Fixtures use the exact log/page strings above. Also re-ran `test_local667_building_stops.py`, `test_local668_*` (27 pass, same before/after).

## 4. Live (cheap arm, own container/meter dir `-p local865`, throwaway postgres, cache+pool off) — `run_local865_live.sh`
- **Palais Lascaris, Nice, 6 stops → 6/6**: Raquel (panneau…), Harpe (Harp), The Musical Instrument Collection, The Frescoed and Painted Ceilings, The Grand Staircase, The Palace Chapel. Tour lat/lng `(43.697694, 7.27725)`, **4 m** from the pin (log: `[D4] … source: resolver_p625`, runner: `tour lat/lng … is 4 m from venue pin`). All stops belong to Palais Lascaris; the only other institution named in the text is Musée Masséna, as the palace's own history (2001 instrument transfer).
- **Regression Gardner Boston, 3 stops → 3/3** (The Concert, The Rape of Europa, The Story of Lucretia); tier rich, feature block not reached.

### Honest caveats
- **Budget overrun: ledger total $0.6219 vs cap $0.60 (+$0.022).** The meter did not abort mid-tour; both tours finished. Only one live run (plus a diagnosis run with no tour generation) was made; no re-runs.
- The Palace Chapel narration contains specifics ("historian Bacci", "conservator Mallet", Hospitaller/Rhodes) that I could **not** find in the fetched nice.fr page; they came from the downstream story/search pass, not from my facts, and I did not verify them. Treat that stop's prose as unreviewed. Single run, n=1, no human scoring of the 6 stops.
- Stops 3–6 are rooms/features, not individual objects; Stop 2 "Harpe (Harp)" is the only instrument item.

## Process
Committed explicit files only (no `git add -A`); run logs (`run865_out/`) not committed. Did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md. No `DELETE`; live DB never written; shared `audioura-*` containers untouched.
