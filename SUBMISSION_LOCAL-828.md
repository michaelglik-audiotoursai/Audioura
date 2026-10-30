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


---

## 828B — precision-first rework (bounce of 828(A))

### Why 828(A) was bounced

The first cut dropped the venue's OWN material:

- the Rijksmuseum's own `rijksmuseum.nl/en/stories/...` page and the
  artsandculture `the-night-watch-rijksmuseum` story were dropped;
- Met passages naming the venue's OWN works under its full name —
  "…print is part of the Metropolitan Museum", "The Harvesters has been at The
  Metropolitan Museum…" — were dropped, because the live-bound identity carried
  **no aliases and no official domain** (`name='The Met Fifth Avenue' domain=-`)
  and the LOCAL-668 foreign-museum detector returned ragged fragments
  ("with the others displayed in museums", "print is part of the Metropolitan
  Museum") that were treated as venue names;
- Wikipedia pages ABOUT THE WORKS (Washington Crossing the Delaware, The
  Harvesters) were dropped by a **standalone CITY rule** that fired on any
  "in <City>" phrase — a painting made in Düsseldorf, a crossing at Trenton —
  which would gut the art history on every museum tour.

23 + 12 over-drops across the two bounce logs.

### The fix: precision first

`venue_identity_gate.py` now drops a passage ONLY when its **SUBJECT** is another
venue. Concretely:

1. **SUBJECT** — the passage is about a concretely, **fully-named** OTHER
   institution. Sources: a curated shared-name separate-institution list (Louvre
   Abu Dhabi, Louvre-Lens, the Met Cloisters), a curated famous-venue table, and
   LOCAL-668's detector — but the detector's hit is accepted only when it reads as
   a **real venue name** (`_looks_like_proper_venue_name`): ≤6 words, no
   possessive, no verb/clause word inside, led by a proper noun, not a bare head
   word. Ragged fragments and works-that-mention-a-museum are never a venue.
2. **DOMAIN** — only a **known** OTHER venue's official domain (curated map, or the
   named other-venue's domain). **Never** wikipedia / wikidata / artsandculture /
   britannica / news / the venue's own domain. A Google `/goto?url=` redirect is
   an **unknown** host, not a foreign one (`domain_of` returns '' for it).
3. **CITY** — there is **no standalone city rule**. A city is only ever a property
   of an OTHER venue already named as the subject ("The Catharijneconvent in
   Utrecht…"). A city where a work was made, depicts, or now hangs is never a drop.

Root-cause fix for the thin identity: `build_identity` **self-enriches** from a
curated famous-venue table (aliases + official domain + city), so a bare
`"The Met Fifth Avenue"` request is recognised as the Metropolitan Museum of Art
and its own works are kept.

Own name / any alias → never dropped. The module stays pure (no network/LLM/DB).

### Precision test on REAL research

During the two live tours the gate recorded every passage it evaluated (text +
URL + decision) via `LOCAL828_CAPTURE` into
`fixtures/local828b_research_fixtures.jsonl` — **68 real passages (38 Rijksmuseum
+ 30 Met)**. `fixtures/local828b_other_venue_fixtures.jsonl` holds 4 real
other-venue passages that must drop, including the exact Catharijneconvent bleed.
`test_local828_venue_identity_gate.py::RealResearchPrecision` replays them:

```
[LOCAL-828B precision] real-research drop counts (after):
    Rijksmuseum: evaluated=38 dropped=0
    The Met Fifth Avenue: evaluated=30 dropped=0
    other-venue fixtures dropped: 4/4
```

- **zero** own-venue passages dropped,
- **zero** work-history passages dropped for a city mention — explicitly pinned:
  "Washington Crossing the Delaware … completed in Germany" and "The Harvesters
  has been at The Metropolitan Museum of Art in New York City since 1919" are
  **kept** (828(A) dropped both),
- the **Catharijneconvent** paragraph (and the Louvre Abu Dhabi / Art Institute of
  Chicago / Albertina siblings) are dropped, each by **subject**.

Before → after, same real passages: Rijks 2 own-venue drops → 0; Met 10 own/work
drops → 0; other-venue still 4/4.

### Tests

`test_local828_venue_identity_gate.py` — **37 pass** (the standalone
city-contradiction class replaced by `CityIsNotAStandaloneDrop`; added
`RealResearchPrecision`). Regressions **214 passed / 3 skipped** across
828 / 668 / 585 / 802 / 823 / 826 / 811 / 813 / 827; meter guards 819 / 820 / 822
**61 pass**.

### Live — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-828B`, cap $0.60)

`subscribed` merged first so the LOCAL-827 whole-task ledger mount
(`~/.audioura_task_budgets → /task_budgets`, `AUDIOURA_TASK_BUDGET_DIR`) and the
meter-log cap apply across both tour containers. Cheap museum arm, pool off,
`gpt-4.1-mini` + serper. Log: `submission_artifacts/local828b_live.log`.

| Tour | Delivered | Other-venue paragraph | Ledger |
|------|-----------|-----------------------|--------|
| The Met Fifth Avenue, New York | **5/5** | none | $0.2188 |
| Rijksmuseum, Amsterdam, Netherlands | 3/5 (see below) | none | $0.2518 |

**Whole-task ledger: $0.4706 / $0.60 — under budget.**

**Drop lines (whole run): exactly one**, and it was a residual false positive the
gate then fixed:

```
[LOCAL-828] other-venue passage dropped Kennedy’s donation changed the museum  <google /goto url>
```

"Kennedy's donation changed the museum's holdings…" is the Met's OWN donation
story, not another venue. `names_foreign_museum` had swept the clause into a
"name". The `_looks_like_proper_venue_name` guard was tightened (reject
possessives, interior verb/clause words, >6-word runs, a bare person+head) and the
captured fixtures re-replayed: **0 drops**. No other-venue drop line fired on the
Met; the Catharijneconvent bleed from the original bug did not recur.

### The Rijksmuseum 3/5 — NOT the venue-identity gate

The Met shipped 5/5. The Rijksmuseum shipped 3/5 — but the gate dropped **0**
Rijksmuseum research passages (the capture file proves it: `dropped=0`), so it
removed no evidence. The original **828(A) Rijksmuseum run also delivered 3/5**
(`submission_artifacts/local828_rijksmuseum_tour.txt`, 3 stop headers). The LEAD's
hypothesis — the gate dropped the Rijks own-domain/artsandculture passages, costing
two stops — is therefore **disproven**: with precision-first the gate keeps every
Rijks passage and the tour still delivers 3/5.

The 3/5 is produced downstream by the **D511 / LOCAL-487 story-quality gate**
("5 stop(s) have NO VALID STORY by Michael's bar: 3+ consecutive sentences, one
person, an action and something at stake" — log lines 1283–1286) plus the
LOCAL-826 museum-canon pass, both independent of venue identity. That is a
story-gate / canon concern, not a venue-research-scope concern — the same boundary
the ticket draws for the false "N exhibitions on view" line (LOCAL-826B's job, not
828's). A gate-off re-run to re-confirm the 3/5 was not re-executed because the
$0.60 ledger ($0.129 headroom) does not fit another ~$0.25 tour; the 0-drop
capture already establishes the gate is not the cause.

### Files (828B)

**Modified**
- `venue_identity_gate.py` — precision-first rework (subject-only drops; curated
  famous-venue table + self-enriching identity; proper-venue-name guard; curated
  other-venue domain map; standalone city rule removed; `LOCAL828_CAPTURE` hook).
- `test_local828_venue_identity_gate.py` — `CityIsNotAStandaloneDrop` +
  `RealResearchPrecision` (real-fixture replay).
- `run_local828_container.py` — cap $0.60; forbidden-term check keyed on
  other-institution names (never a bare city).
- `run_local828_live.sh` — `TASK_BUDGET_ID=LOCAL-828B`, cap $0.60, LOCAL-827 ledger
  mount, `LOCAL828_CAPTURE` wired.

**New**
- `fixtures/local828b_research_fixtures.jsonl` — 68 real captured research passages.
- `fixtures/local828b_other_venue_fixtures.jsonl` — 4 real other-venue must-drop
  passages (incl. the exact Catharijneconvent bleed), with provenance.
- `submission_artifacts/local828b_live.log` — the budget-enforced live run.
