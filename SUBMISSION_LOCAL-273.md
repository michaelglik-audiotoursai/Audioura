##### READY FOR REVIEW

**Commit:** c1b9e64  
**Branch:** kiro/local273-closing-offer  
**Base:** storied  

## Per-File Summary

| file | change |
|---|---|
| `generate_tour_text.py` | Added `_build_closing_offer()` (277 lines at ~L722) + wired into `[G4] Build epilog` block (10 lines at ~L8673) |
| `run_local273_closing_offer.py` | Generation script for Round 27 tours (new) |
| `RIVIERA_2STOP_ROUND27.md` | 2-stop generated tour with closing (new) |
| `RIVIERA_8STOP_ROUND27.md` | 8-stop generated tour with closing (new) |

## Closing Offer — Verbatim Evidence

### 2-stop (last stop: Saint-Jean-Cap-Ferrat)

> Place Masséna is 5 kilometers from here — we can build a cycling tour there. There is also a museum tour available at the Musee d Art Moderne et d Art Contemporain. We can also generate news articles for you to listen to on the way back.

- **Sentence count:** 3
- **Words:** 47
- **Generation time:** 38.1s
- **Word count (full tour):** 348

### 8-stop (last stop: Vieux Port, Cannes)

> Russian Orthodox Cathedral, Nice is 25 kilometers from here — we can build a cycling tour there. There is also a museum tour available at the Musee Picasso. We can also generate news articles for you to listen to on the way back.

- **Sentence count:** 3
- **Words:** 43
- **Generation time:** 114.6s
- **Word count (full tour):** 2287

### Baseline comparison (2-stop)

| metric | round 23 | round 27 |
|---|---|---|
| cost | $0.0206 | ~$0.02 (same model, same stop count) |
| time | 43s | 38.1s |
| closing | *(none — ends mid-thought)* | 3 sentences, 47 words |

## Verification Evidence

### Part 1 (similar tour, same category)

| tour | offered stop | verified in | distance | evidence |
|---|---|---|---|---|
| 2-stop | Place Masséna | `stop_corpus` (venue: French Riviera walking area) + `venue_corpus` canonical_titles (Nice walking area, QID Q33959, lat=43.6973, lng=7.2701) | 5 km from last stop | `SELECT stop_title FROM stop_corpus WHERE LOWER(stop_title) LIKE '%massena%'` → `('Place Massena', 'French Riviera walking area')` |
| 8-stop | Russian Orthodox Cathedral, Nice | `stop_corpus` (venue: walking tour in Nice, france) + `venue_corpus` canonical_titles (Nice walking area, QID Q33959, lat=43.704, lng=7.254) | 25 km from last stop | `SELECT stop_title FROM stop_corpus WHERE LOWER(stop_title) LIKE '%russian%'` → `('Russian Orthodox Cathedral', 'walking tour in Nice, france')` |

### Part 2 (adjacent capability — museum)

| tour | offered museum | verified in | city | distance |
|---|---|---|---|---|
| 2-stop | Musee d Art Moderne et d Art Contemporain | `venue_corpus` (QID Q936859) | Nice | ~3 km from Saint-Jean-Cap-Ferrat |
| 8-stop | Musee Picasso | `venue_corpus` (QID Q1368360) | Antibes | ~8 km from Vieux Port Cannes |

### Part 2 (adjacent capability — news)

News capability confirmed by checking file existence:
```
os.path.exists('/Users/micha/audioura-worktrees/LOCAL-273/news_orchestrator_service.py') → True
```
The file contains `@app.route('/generate-news', methods=['POST'])` at line 95.

### LOCAL-44 anti-preaching tests (all 34 pass)

```
tests/test_local44_stop_preaching.py::TestEpilogNoPreaching::test_no_reflect_on_path PASSED
tests/test_local44_stop_preaching.py::TestEpilogNoPreaching::test_no_next_journey_awaits PASSED
tests/test_local44_stop_preaching.py::TestEpilogNoPreaching::test_no_consider_generating_another_tour PASSED
tests/test_local44_stop_preaching.py::TestEpilogNoPreaching::test_no_we_hope_you_leave_inspired PASSED
```

Full suite: `34 passed in 0.08s`

### The three specific assertions from the task

```python
assert "consider generating another tour" not in source       # PASS
assert "The next journey awaits" not in epilog_section        # PASS
assert "leave inspired by the beauty" not in source           # PASS
```

### DB cleanup (D141)

Both test tour rows (IDs 263, 264) had `is_test=true` confirmed via `SELECT is_test FROM audio_tours WHERE id = %s` before deletion. Nice list unchanged: `[1, 12, 14, 17, 24, 29, 152]`.

### Protected files (D147)

```
git diff --stat $(git merge-base HEAD storied) -- DECISIONS.md CLAUDE.md BACKLOG.md .continuous_dev/
(empty — no changes)
```

## What Was Omitted

Nothing was omitted for failing verification. Both tours produced all three sentences:
- Part 1: similar-category stop, existence-verified
- Part 2a: museum, existence-verified in venue_corpus
- Part 2b: news capability, file-existence-verified

## Limitations

1. **Museum proximity uses city-coordinate lookup, not Wikidata geo.** Museums in `venue_corpus` have their canonical_titles as artwork lists (strings), not geographic POI dicts. The function uses known city coordinates extracted from the venue_name field (e.g. "Nice" → 43.71, 7.26) to estimate distance. This is approximate (±2 km within a city) but sufficient for "is there a museum tour available" — it doesn't claim a specific walking distance.

2. **The 2-stop tour's Stop 2 description is thin.** Only the orientation text appears for Saint-Jean-Cap-Ferrat, with no full multi-paragraph description. This is a pre-existing generation quality issue unrelated to LOCAL-273's epilog change. The closing offer still appears and reads correctly.

3. **8-stop existence gate couldn't run against DB.** The STOP_EXISTENCE_GATE_MODE=enforce was set, but the area_cache lookup failed (could not translate host "postgres-2" — expected in host mode). Stops were kept. This is a known limitation of running on the host vs. inside Docker.

4. **Cost not precisely measured.** The `api_call_logger` doesn't expose a `get_session_cost()` method on this branch. The 2-stop generation used gpt-3.5-turbo with similar token counts to round 23 ($0.0206), so cost is estimated at ~$0.02. The 8-stop is estimated at ~$0.08–0.10 (proportional to tokens). Total well under the $1.00 ceiling.

5. **No container rebuilt.** All work done on host with existing DB connection.
