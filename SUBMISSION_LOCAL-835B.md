# SUBMISSION — LOCAL-835B (BOUNCE of LOCAL-835)

**Branch:** `LOCAL-835B-guard-every-path`
**Base:** subscribed (`82b6f374`, the LOCAL-835 merge) — `git merge-base --is-ancestor 82b6f374 HEAD` → 0.

LOCAL-835 wired the activity-provider guard into the FRESH places path and ran
it **once**, after discovery. The LEAD re-run ("Kiteboarding lessons in Mui Ne,
Vietnam" (5) → tour 868: **Sea Horse Resort, Source Kiteboarding, Sandals
Restaurant, The Bar, Jibe's Beach Club** — one kite school) proved two other
ADD/KEEP paths put the food/leisure stops right back after the guard: the
**LOCAL-788B map override** kept the LLM-excluded resort/cafe/bar because
`places_search` confirms they EXIST, and the **D545 replenish ladder** (the kite
request misclassifies as a restaurant tour) ADDed restaurants/bars.

This change makes it **one guard, every path**: the activity-provider check now
runs at every point a stop is ADDED or KEPT, and the maps-first PROVIDER
discovery is turned on for a provider request so the honest answer is *real
providers* (or an honest shortfall), never padding.

---

## 1. One guard, every path — call sites (file:line)

The guard is `category_match_guard.filter_off_category_activity` /
`candidate_is_activity_provider` (keyed off `requested_activity(request)`, a
no-op for a non-provider or a food request). Already-wired LOCAL-835 sites are
listed for completeness; the **NEW** LOCAL-835B sites are the bounce fix.

| # | Path | File:line | What it does |
|---|------|-----------|--------------|
| 1 | Initial discovery (post-PHASE-3C) | `generate_tour_text.py:15559` (`_foca835`) | 835 — drops off-category candidates after discovery |
| 2 | PHASE 3C maps top-up | `generate_tour_text.py:15979` (`_foca835r`) | 835 — guards escalation-ladder candidates |
| 3 | PHASE 3C widened replenish | `generate_tour_text.py:16047` (`_foca835w`) | 835 — guards the ×2-bbox widened candidates |
| 4 | **788B PHASE 4 map override** | **`generate_tour_text.py:11674–11698`** | **NEW** — before honouring a `places_search` map override, `candidate_is_activity_provider` on the single POI; verdict `False` → **`_p4_oc_block=True`**, override REFUSED, LLM exclusion stands (`[LOCAL-835B] map override REFUSED`) |
| 5 | **Provider discovery turn-on** | **`generate_tour_text.py:15929–15950`** | **NEW** — `requested_activity` non-food forces `_p3c_kind='business'` so the maps-first PROVIDER escalation actually runs (`kiteboarding lessons` classifies as `'landmark'`, which otherwise skips it) |
| 6 | **D545 places-first replenish** | **`generate_tour_text.py:18615–18629`** (`_foca835d`) | **NEW** — guards `replenish_with_escalation('dining', …)` candidates before the ADD loop |
| 7 | **D545 LLM `propose_replacements` round** | **`generate_tour_text.py:18674–18686`** (`_foca835l`) | **NEW** — guards each LLM proposal before ADD (the path that added Sandals / The Bar / Jibe's) |
| 8 | **Generic replenish helper (D556 / LOCAL-576 / LOCAL-818)** | **`generate_tour_text.py:2820–2851`** (inside `replenish_to_count`, new `request_text` param) | **NEW** — the ONE helper every generic "places to visit" round flows through; STRICT for a provider request (keep only verdict `True`, drop `None`/`False` padding). Request passed at all 4 call sites: `18898` (D556), `19102` (`_cc`), `19978` (LOCAL-576 pre-writing), `20112` (LOCAL-818 refill) |
| 9 | **FINAL pre-narration pass** | **`generate_tour_text.py:20033–20060`** (`_foca835f`) | **NEW** — last net on the full `poi_list` before PHASE 5, with named anchors |
| 10 | **Pool reuse (830)** | **`stop_pool_orchestrator.py:724–738`** (`_foca835p`) | **NEW** — activity guard alongside the LOCAL-830 business guard (catches a pooled beach club / landmark the restaurant-only 830 guard misses) |

**816** only widens the containment *scope* (`generate_tour_text.py:2878`); it
adds no stops, so its refills flow through the guarded replenish helper + the
final pass. No separate guard needed.

## 2. A resort/hotel/bar/beach club is off-category unless it IS the provider

The bounce's "Sea Horse Resort" survived because `classify_place("Sea Horse
Resort", "Resort")` → `None` (unknown) and the guard never drops an
unclassifiable place. A RESORT/hotel is a place you stay, not a provider. Added
the lodging/leisure words to `category_match_guard._GENERIC_LANDMARK_WORDS`
(`resort, hotel, motel, hostel, guesthouse, villa, bungalow, lodge, inn, spa,
beach club, beach resort, …`). Ordering is preserved: the activity-word /
provider-noun check runs FIRST, so **"X Kite School at Y Resort"** still reads as
a provider and is kept. Story facts that merely say "near kite spots" never make
a venue a provider — the verdict is on the venue's own name/type only.

## 3. Honest shortfall, never pad

The generic "places to visit" proposer returns a bare `{name, why}` with no
category, so a landmark like "Fairy Stream" classifies as `None`. In the generic
replenish helper a `None` from that proposer is padding by construction (the real
providers already came from the maps-first PROVIDER discovery), so for a provider
request the helper keeps **only** recognised providers and drops the rest — the
count stays short rather than being padded. The honest-shortfall intro line is
unchanged.

## 4. Tests — from the exact bounce log lines

`tests/test_local835b_guard_every_path.py` (11 tests), plus the 20 existing
LOCAL-835 tests still green — **31 passed**.

* **Sea Horse override refused** — `candidate_is_activity_provider` is `False`
  for `Sea Horse Resort / Resort`, `Cham Garden Restaurant`, `Joe's Cafe`,
  `Pogo Beach Bar` (the exact names + categories from log lines 193/197/198/199);
  a real `Source Kiteboarding` stays overridable (`True`).
* **D545 additions dropped** — `Sandals Restaurant`, `The Bar`,
  `Jibe's Beach Club` (log lines 441/535/570) all drop; the full tour-868 list
  reduces to `Source Kiteboarding` only.
* **Scuba providers-only** — dive centres kept, bar/restaurant/beach dropped.
* **Structural wiring** — asserts the guard is present at the 788B override
  (refusal gates the keep), both D545 rounds, the final pass and pool reuse.

```
python3 -m pytest tests/test_local835_activity_on_category.py \
                  tests/test_local835b_guard_every_path.py -q
→ 31 passed
```

Broader guard suite (`-k "791 or 790 or 830 or category or pool or 835 or 576 or
788"`): **361 passed, 20 skipped, 1 failed** — the one failure
(`test_local820_meter_wiring.py::…[run_local830_live.sh]`) is **pre-existing and
unrelated** (a stale `run_local830_live.sh` missing meter-contract signals; not
touched by this change).

## 5. Live run — BUDGET ENFORCED

`run_local835b_live.py`, Mac-local, cheap arm, pool OFF, budget enforced
(`TASK_BUDGET_ID=LOCAL-835B TASK_BUDGET_USD=0.80`, `LiveRunMeter` reserve gate +
per-task JSON ledger). Same documented no-mount diagnostic pattern as
`run_local834_live.py`. Never writes the live DB; never touches the shared
`audioura-*` containers.

```
CHEAP_ARM_CATEGORIES=museum,walking,restaurant,facility,specialized
NARRATION_MODEL=gpt-4.1-mini   RESEARCH_BACKEND=serper   SERP_PROVIDER=serper
DISABLE_STOP_POOL=1
```

Evidence: `~/Audioura/reports/local835b/gen_835b_final.log`,
ledger `_local835b_meterlogs/LOCAL-835B.json`.

**Kiteboarding lessons in Mui Ne, Vietnam (5 requested)** — **4/5, PASS
(honest shortfall, no off-category, no padding), $0.2427 < $0.45**
1. Muine Kitesurf School  2. C2Sky KiteSurfing  3. Surfpoint Vietnam  4. Mui Ne
Bay Kite School — all kite providers from the maps-first PROVIDER discovery.

**Scuba diving courses in Nha Trang, Vietnam (4 requested)** — **4/4, PASS
(providers only), $0.2315 < $0.45**
1. Vietnam Diving and Training Nha Trang  2. Sailing Club Nha Trang (= Sailing
Club Divers, "Nha Trang's Best Dive Center")  3. Nha Trang Xua  4. Rainbow Divers.

The guard fired at every path in the live log:
* `[LOCAL-835B] map override REFUSED` for Deja Vu / Sand Dunes Restaurant / Rang
  Cafe / Mui Ne Seafood / Joe's Cafe (kite); Nha Trang Seafood Restaurant / The
  Rooftop Bar / Alley Cafe (scuba);
* `[LOCAL-835B] provider request … → maps-first PROVIDER discovery (kind
  'landmark'→'business')` on both tours;
* `[LOCAL-835B] D545 LLM replenish guard dropped 3` (kite) / `2` (scuba);
* `[LOCAL-835B] FINAL pre-narration guard` (all on-category kite; dropped 1 scuba);
* `[LOCAL-835B] replenish guard dropped` **Mui Ne Fishing Village**, **Jibe's
  Beach Club**, **Mui Ne Sand Dunes** (kite), **Hon Mun Marine Protected Area**
  (scuba) — the exact off-category venues the bounce flagged, now never padded in.

## 6. Files changed

* `category_match_guard.py` — lodging/leisure words added to
  `_GENERIC_LANDMARK_WORDS`.
* `generate_tour_text.py` — the 788B override refusal, provider-discovery
  turn-on, D545 places-first + LLM guards, the `replenish_to_count` `request_text`
  param + strict guard (passed at all 4 callers), the FINAL pre-narration pass.
* `stop_pool_orchestrator.py` — activity guard on pool reuse.
* `tests/test_local835b_guard_every_path.py` — new tests.
* `run_local835b_live.py` — the budget-enforced live proof.

Only these files are committed (`git add` by path, no `git add -A`). The live
run's generated tour `.txt`/`.json`, `_local835b_meterlogs/`, and the prompt/debug
dumps it rewrote were NOT committed.
