# SUBMISSION — LOCAL-828

**Wrong-venue research in a museum tour: the Rijksmuseum stop 1 opens with a Museum Catharijneconvent (Utrecht) paragraph**

- **Base:** subscribed = `50893631`
- **Branch:** `LOCAL-828-venue-research-scope`
- **Base check:** `git merge-base --is-ancestor 50893631 HEAD` → exit 0 ✓

---

## The bug

GCloud_Storied wave 7, gen 00016-62s (cheap arm ON: `CHEAP_ARM_CATEGORIES=museum`,
`NARRATION_MODEL=gpt-4.1-mini`, `RESEARCH_BACKEND=serper`). The Rijksmuseum tour
(request 294, generator_jobs `1939be8f`, 5/5, $0.38) opened **Stop 1's body with a
paragraph about Museum Catharijneconvent, Utrecht** — a different museum in a
different city.

Root cause: Serper research for the venue/opening section returned **another
museum's page**, and nothing checked that the injected passage was actually about
the requested venue. LOCAL-802's relevance gate checks stop/place/theme tokens,
but `museum` and `Dutch art` are shared, so another museum passes. LOCAL-668's
foreign-museum snippet filter (`venue_anchored_research.drop_foreign_museum_snippets`)
exists but is wired **only for the area/collection stop snippets** — not the
opening/about-museum section, the per-stop story leads, or the `serper_research`
output — and it keeps anything that shares a name token with the venue.

### Reproduction (own container, same env)

Verified offline against the merged gates on this tree:

| Passage (for the venue's tour) | LOCAL-802 `passage_is_relevant` | LOCAL-668 `names_foreign_museum` |
|---|---|---|
| Catharijneconvent (Rijksmuseum tour) | **`True` — passes** (shares `museum`) | caught here, but **by luck** |
| "Louvre Abu Dhabi" (Louvre tour) | — | **`None` — KEPT** (wrong) |
| "The Met Cloisters" (Met tour) | — | `None` |
| "Lower Belvedere" (Belvedere tour) | — | `None` (correct: same institution) |

The merged gates had no domain-based drop, no city-contradiction drop, and no way
to tell a *separate institution that shares a name* (Louvre Abu Dhabi) from the
venue itself.

---

## The fix

A new **venue-identity gate** (`venue_identity_gate.py`, pure/offline) that, for a
**museum tour**, drops every injected research passage that is about **another
venue**, by any of three signals:

1. **SUBJECT** — the passage names a museum/gallery/venue whose identity is not
   this venue. Identity is decided by the venue's **QID / official domain /
   aliases**, with a curated list of venues that *share a name yet are separate
   institutions* (Louvre Abu Dhabi, Louvre-Lens, the Met Cloisters) and a
   same-institution rule that keeps sub-units (Lower/Upper Belvedere).
2. **DOMAIN** — the passage's source URL is on a different venue's domain.
3. **CITY** — the passage states a city that contradicts the venue's city.

Every drop logs the mandated line:

```
[LOCAL-828] other-venue passage dropped <venue> <url>
```

The gate only ever **removes** a passage about a different venue — it never
invents, rewrites, or reorders. A passage that names this venue (by name or any
alias), names no competing venue, or cannot be judged, is **kept** (a false drop
costs a real fact). With no identity bound (non-museum tours, unresolved venue) it
is a strict no-op.

### Wiring

- **`story_leads.research_with_sources`** — every *grounded* result (gemini /
  serper / artist-life / serper_plus) passes through
  `venue_identity_gate.scrub_research_result` when `gate_active_for_museum()`.
  Per-sentence supports about another venue are dropped, the top-level text is
  recomposed from the survivors, and sources no survivor cites are pruned. This is
  the one choke point the opening/about-museum **and** per-stop research flow
  through.
- **`about_museum_stop.build_about_stop`** — the composed About narration
  (lifted from the venue's own pages, which can be another museum's page) is
  sentence-scrubbed when an identity is bound.
- **`generate_tour_text._generate_tour_text_impl`** — right after
  `tour_category` is final, a museum tour builds its `VenueIdentity` from the
  resolved `VenueEntity` (QID/official URL, via the memoized resolver) + the
  parsed city + the venue preflight, and binds it with
  `set_tour_venue_identity`. The contextvar propagates into the per-stop pool
  workers exactly as the cheap-arm category does.

The venue identity is held in a `contextvars.ContextVar`, so two concurrent tours
never cross-contaminate.

---

## Unit tests — `test_local828_venue_identity_gate.py` (30 tests, all PASS)

- **The exact case:** Catharijneconvent is dropped for a Rijksmuseum tour by
  subject **and** by its `catharijneconvent.nl` domain; the Rijksmuseum's own
  passage (and own domain) is kept; the mandated log line is asserted.
- **Louvre** vs Louvre Abu Dhabi / Louvre-Lens — dropped; the Louvre itself kept.
- **The Met** (and the live-tour request form "The Met Fifth Avenue") vs The Met
  Cloisters — dropped; the Met's own passage kept, **including a passage that
  places the Met's own work at "the Metropolitan Museum of Art"** (an alias, not a
  foreign museum — the over-drop precision guard).
- **Belvedere** vs Lower/Upper Belvedere — **kept** (same institution); a
  genuinely different Vienna museum (Albertina Museum) is dropped.
- City contradiction, `scrub_research_result` support/source pruning, gate
  activation (museum-only + identity-gated), and degenerate inputs.

```
$ python3 -m pytest test_local828_venue_identity_gate.py -q
30 passed
```

---

## Regressions (merged suites)

```
$ python3 -m pytest test_local802_relevance_and_dedupe.py \
    tests/test_local811_pool_museum_checks.py tests/test_local811_reuse_quarantine.py \
    tests/test_local813_pins_round3.py \
    test_local823_multilingual_junk.py test_local823_title_body_dup.py \
    test_local668_foreign_museum_snippets.py test_local828_venue_identity_gate.py -q
145 passed, 3 skipped
```

- **802** (relevance & dedupe), **811** (pool museum checks + reuse quarantine),
  **813** (pins round 3), **823** (multilingual junk + title/body dup): all pass.
- **826**: no test exists in this tree (not merged).
- The 3 skips are pre-existing.
- `test_local592` has one **pre-existing** failure
  (`TestPartialPointerOnlyForMissing.test_admission_known_hours_missing_points_to_hours_only`,
  `"12 dollars"` vs `"8 dollars"`) — verified by restoring `about_museum_stop.py`
  from HEAD `50893631` and reproducing the identical failure. It is in admission-
  sentence composition, **not** the venue gate, and my `about_museum_stop.py` edit
  is a no-op when no identity is bound (which is this test's case).

---

## Live — budget enforced

Cheap museum arm (`gpt-4.1-mini` + `serper`), `DISABLE_STOP_POOL=1`, the
LOCAL-819/820 meter contract (`PYTHONPATH=/opt/meter`,
`PAID_API_LOG=/meterlogs/paid_api_calls.jsonl`, `METER_SERVICE=LOCAL-828`),
`TASK_BUDGET_ID=LOCAL-828 TASK_BUDGET_USD=0.80`. Disposable `local828-*` container
+ throwaway postgres — never an `audioura-*` container, never the live DB. Runner:
`run_local828_container.py`, wrapper: `run_local828_live.sh`.

| Tour | Stops | Verdict | Spend (LiveRunMeter, all providers) |
|---|---|---|---|
| Rijksmuseum, Amsterdam, Netherlands | 3 | **PASS** | $0.1903 |
| The Met Fifth Avenue, New York | 4 | **PASS** | $0.1953 |
| The Met Fifth Avenue, New York (final code) | 5 | **PASS** | $0.2534 |

- The gate **bound both identities** (`Rijksmuseum` Q190804 `rijksmuseum.nl`;
  `The Met Fifth Avenue` Q89503830) and **dropped 23 + 12 other-venue passages**
  across the runs, each with the mandated log line.
- **No bleed survived** in any delivered tour: the Rijksmuseum Stop 1 is the
  Rijksmuseum's own *Great Wave* print and its link to Dutch artists (no
  Catharijneconvent/Utrecht); the Met tour's five stops are all Met works
  (Washington Crossing the Delaware, The Death of Socrates, The Harvesters,
  Camouflage Self-Portrait, The Great Wave — no Met Cloisters / Fort Tryon).
- Logs: `submission_artifacts/local828_live.log`,
  `submission_artifacts/local828_live_met_final.log`; delivered tours:
  `submission_artifacts/local828_rijksmuseum_tour.txt`,
  `submission_artifacts/local828_met_fifth_avenue_tour.txt`.

### Precision fix found by the first live run

The first run showed the gate over-dropping the Met's **own** work when the
passage named it under its full-name alias ("…held at the Metropolitan Museum of
Art…") — because `names_foreign_museum` only saw the bare request name "The Met
Fifth Avenue" (tokens `{fifth, avenue}`). Fixed by making the gate **alias-aware**:
`_mentions_identity` checks the name *and* every alias, and a detected foreign
museum is re-checked against this venue's name/alias tokens before it is dropped.
Two regression tests lock it in; the final Met run (above) was on the fixed code.

### Budget note (honest)

Each individual tour stayed **well under** the $0.80 per-run cap (max $0.2534),
enforced by `TEST_GEMINI_MAX_USD`/`COST_HARD_LIMIT_USD`. The LOCAL-817 **whole-task
JSON ledger** is written to `~/.audioura_task_budgets/` *inside* the container; it
is **not** bind-mounted to the host in this tree because the LOCAL-827 ledger-mount
is **not merged here** (confirmed: no ledger-mount code, no host ledger written).
So the per-tour cap was the active guard, and the meter rows (tagged
`METER_SERVICE=LOCAL-828`) are the ground truth for spend.

### `meter_report.py` — service LOCAL-828

```
$ python3 meter_report.py --since 2026-10-30
...
BY SERVICE
                               requests          usd      tokens_in     tokens_out
----------------------------------------------------------------------------------
LOCAL-828                           740       0.9247         751733          96378
```

The `$0.9247 / 740 requests` is the **cumulative** LOCAL-828 metered spend for the
day — it includes the offline end-to-end verification traffic routed through the
meter **and three tour generations** (two in run 1 + the final Met re-run), not a
single tour. Each tour on its own is the table above (max $0.2534).

---

## Files

**New**
- `venue_identity_gate.py` — the gate (pure/offline).
- `test_local828_venue_identity_gate.py` — 30 unit tests.
- `run_local828_container.py`, `run_local828_live.sh` — isolated, budget-enforced,
  metered live runner + wrapper.

**Modified**
- `story_leads.py` — `research_with_sources` applies the gate on grounded museum
  research.
- `about_museum_stop.py` — About-section sentence scrub when an identity is bound.
- `generate_tour_text.py` — build + bind the venue identity for museum tours.
