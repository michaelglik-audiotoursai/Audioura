##### READY FOR REVIEW

**Commit:** 085fe93
**Branch:** kiro/local275-closing-restaurant-and-treats
**Base:** storied

## Per-File Summary

| file | change |
|---|---|
| `generate_tour_text.py` | Modified `_build_closing_offer()`: Part 2 now tries restaurant tour (verified via `audio_tours`) before museum fallback, with Treat Page mention folded in. Sentence budget splits when Part 1 absent to maintain exactly 3. |
| `run_local275_closing_restaurant_treats.py` | Generation script for Round 29 tours (new) |
| `RIVIERA_2STOP_ROUND29.md` | 2-stop generated tour with restaurant+treats closing (new) |
| `RIVIERA_8STOP_ROUND29.md` | 8-stop generated tour with restaurant+treats closing (new) |

## Closing Offer — Verbatim Evidence

### 2-stop (last stop: Corniche d'Or, Théoule-sur-Mer)

> Russian Orthodox Cathedral, Nice is 35 kilometers from here — we can build a cycling tour there. If you would like to eat nearby we can build you a restaurant tour, and the Treat Page shows whether there are real savings at local shops and restaurants around here. We can also generate news articles for you to listen to on the way back.

- **Sentence count:** 3
- **Words (closing):** 63
- **Generation time:** 41.5s
- **Word count (full tour):** 547
- **Cost:** $0.0095

### 8-stop (last stop: Cap d'Antibes)

> Russian Orthodox Cathedral, Nice is 22 kilometers from here — we can build a cycling tour there. If you would like to eat nearby we can build you a restaurant tour, and the Treat Page shows whether there are real savings at local shops and restaurants around here. We can also generate news articles for you to listen to on the way back.

- **Sentence count:** 3
- **Words (closing):** 63
- **Generation time:** 123.7s
- **Word count (full tour):** 2107
- **Cost:** $0.0482 (cumulative; $0.0387 for 8-stop alone)

### Baseline comparison (2-stop)

| metric | round 23 | round 27 (LOCAL-273) | round 29 (LOCAL-275) |
|---|---|---|---|
| cost | $0.0206 | ~$0.02 | $0.0095 |
| time | 43s | 38.1s | 41.5s |
| closing | *(none)* | 3 sentences (museum+news) | 3 sentences (restaurant+treats+news) |

## Verification Evidence

### Part 1 (similar tour, same category) — Unchanged from LOCAL-273

| tour | offered stop | verified in | distance | evidence |
|---|---|---|---|---|
| 2-stop | Russian Orthodox Cathedral, Nice | `stop_corpus` (venue: walking tour in Nice, france) | 35 km from last stop | `SELECT stop_title FROM stop_corpus WHERE LOWER(stop_title) LIKE '%russian%'` → `('Russian Orthodox Cathedral', 'walking tour in Nice, france')` |
| 8-stop | Russian Orthodox Cathedral, Nice | `stop_corpus` (venue: walking tour in Nice, france) | 22 km from last stop | Same query, same evidence |

### Part 2 (restaurant tour — NEW in LOCAL-275)

| tour | offered capability | verified in | evidence |
|---|---|---|---|
| 2-stop | Restaurant tour | `audio_tours` id=17, `is_test=false` | `SELECT id, tour_name, lat, lng FROM audio_tours WHERE LOWER(request_string) LIKE '%restaurant%'` → `(17, 'restaurants tour in old city of Nice, France - Restaurant Tour', 43.69522, 7.27023)` |
| 8-stop | Restaurant tour | Same — id=17, 21.6 km from last stop | Same evidence; haversine from Cap d'Antibes (43.541, 7.107) to restaurant tour coords (43.695, 7.270) = 21.6 km < 40 km threshold |

### Part 2 (Treat Page — NEW in LOCAL-275)

| evidence type | detail |
|---|---|
| App screen | `audio_tour_app/lib/screens/treats_screen.dart` calls `/treats-near/{lat}/{lng}` |
| Endpoint config | `audio_tour_app/lib/config/endpoints.dart` → `Service.treats` → port 5007 |
| Docker service | `docker-compose-master.yml:245` → treats service, Dockerfile.treats |
| Location anchoring | Closing uses last stop coords (2-stop: 43.4974, 6.9326; 8-stop: 43.5410, 7.1073) |
| No savings claimed | Exact phrasing: "shows **whether** there are real savings" — never asserts they exist |

### Part 3 (news) — Unchanged from LOCAL-273

News capability confirmed: `news_orchestrator_service.py` exists, contains `@app.route('/generate-news', methods=['POST'])` at line 95.

### LOCAL-44 anti-preaching tests (all 34 pass)

```
tests/test_local44_stop_preaching.py: 34 passed in 0.08s
```

Key assertions:
```python
assert "consider generating another tour" not in source       # PASS
assert "The next journey awaits" not in epilog_section        # PASS
assert "leave inspired by the beauty" not in source           # PASS
```

### DB cleanup (D141)

Tour IDs 272, 273 created with `is_test=true`, confirmed via `SELECT is_test FROM audio_tours WHERE id = %s` before deletion. audio_tours count: 143 → 143. Nice list unchanged: `[1, 12, 14, 17, 24, 29, 152]`.

### Protected files (D147)

```
git diff --stat $(git merge-base HEAD storied) -- DECISIONS.md CLAUDE.md BACKLOG.md .continuous_dev/
(empty — no changes)
```

### Sentence budget logic

When Part 1 (similar tour) verifies:
- S1: similar tour → S2: restaurant+treats (combined) → S3: news = **3 sentences**

When Part 1 does not verify (e.g., last stop already in Nice, all corpus stops <3 km away):
- S1: restaurant tour → S2: Treat Page (standalone) → S3: news = **3 sentences**

Both paths tested and confirmed with simulated tour data.

## What Was Dropped for Failing Verification

- **Museum offer** was not needed in either run — restaurant tour (id=17) verified successfully for both because both tours' last stops were within 40 km of Nice Old City. Museum fallback logic is present but not exercised here.
- **Part 1 (similar tour)** would be omitted if the 8-stop tour's last stop were inside Nice (where all corpus stops are <3 km). The sentence budget split handles this case (tested separately — produces 3 sentences with restaurant + Treat Page split).

## Limitations

1. **Restaurant verification depends on existing tour in `audio_tours`.** There is exactly one restaurant tour (id=17, Nice Old City). If the tour's last stop were >40 km from Nice (e.g., Saint-Tropez at 70 km), no restaurant tour would verify. In that case the function falls back to museum (if nearby) or Treat Page alone.

2. **Treat Page is always mentioned** regardless of whether treats exist near the last stop. This is correct per Michael's spec — the page "shows whether there is a real saving" — but the `treats` table is currently empty. The app handles this gracefully ("No treats available").

3. **The 8-stop tour produced 7 stops** despite requesting 8. This is a pre-existing LLM generation issue unrelated to LOCAL-275's closing change. The closing correctly attaches to the actual last stop.

4. **No container rebuilt.** All work done on host with existing DB connection (D48).

5. **Cost ceiling: $0.0482 total** against $0.60 ceiling — 92% under budget.
