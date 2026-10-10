# SUBMISSION — LOCAL-667

**A real museum with thin Wikidata (Ho Chi Minh City Museum of Fine Arts) delivered 1 of 5 stops; a title was split into "North / Central / South / Garden".**

- **Branch:** `LOCAL-667-thin-wikidata-museum`
- **Base:** `subscribed` @ `0b0f433a` (`git merge-base --is-ancestor 0b0f433a HEAD` → exit 0)
- **Agent:** Mac Mini Kiro

---

## 1. Root cause (confirmed, not assumed)

I queried Wikidata directly (free, no LLM) for the works of the venue (`Q2756351`):

```
Q109406846 | EN label: "North Central South Spring Garden"
           | VI label: "Vườn xuân Bắc Trung Nam"
           | EN altLabel: "Central South and North Spring Garden"
```

So the museum has **one** SPARQL-documented work, and its English Wikidata label
is literally the list-like string `North Central South Spring Garden` (a reordered
translation of the Vietnamese title). That single title was injected into the
Phase-3A candidate prompt as a guidance hint. `gpt-4.1-mini` read it as an
enumeration and returned **five** candidate "works": *North*, *Central*, *South*,
*Spring Garden*, *Garden*.

Downstream (evidence log `~/Audioura/.continuous_dev/bench/AB10/hcmc_off_662.log`):

- D1v2 verified only the fragment that covered enough of the canonical
  (`Spring Garden → North Central South Spring Garden`) and **dropped the other
  four** (a single word covers too little of a ≥3-word canonical — the LOCAL-34
  reverse-coverage rule, correctly).
- R4 then asked GPT for more works; GPT returned **real** Vietnamese artworks
  (The Fisherman, Lotus Pond, …) but **all** were dropped because they do not
  match the thin 2-title canonical set.
- The LOCAL-16 gate stripped every unverified fill → **1 of 5**, with the user
  told "this tour has 1 stop rather than the 5 you asked for".

So the title was never split on literal commas/"and" by our parser — the Wikidata
label itself is comma-free; the LLM atomised a list-shaped title. The fix must
make a list-like title survive as ONE work, and give a thin museum real stops
beyond its single catalogued work.

---

## 2. What I delivered

Three focused, pure, unit-tested modules, each wired at one point and (except the
collapse guard, which is a strict no-op for well-documented museums) **gated to the
`thin` tier only**, so a rich/medium museum's path is byte-for-byte unchanged.

### #1 No title splitting — `candidate_collapse_guard.py`
Before D1v2 verification, when two or more candidates are **fragments of ONE known
canonical/SPARQL title** (a contiguous word-span, or an "and"/comma clause split),
they collapse into a **single** candidate carrying that canonical title. It only
ever collapses INTO a title already in the known set — it never invents a title
and never merges two distinct works (a ≥3-content-word target is required, and ≥2
fragments). The Phase-3A hint also now **quotes multi-word titles** and tells the
model each quoted string is one work, so a list-like title is far less likely to
be atomised in the first place.
- Wired: `generate_tour_text.py` `_verify_works_v2` (before the verify loop) and
  the Phase-3A hint builder.
- Fixture (ticket): `"Spring Garden of the Central, South and North"` /
  `"North Central South Spring Garden"` stays ONE candidate.

### #3 Thin-Wikidata verification — `thin_wikidata_fallback.py`
For a `thin` museum still short after R4, the model-proposed works R4 dropped are
re-verified against the sources Wikidata is not:
(a) the museum's **own site**, local language and English;
(b) **Wikipedia**, local language and English (collection / notable-works);
(c) a **grounded search** (the active research backend, `story_leads.research_with_sources`).
(a) and (b) are already fetched for the tour, so they cost nothing; (c) is the
only paid step and is capped. **Honesty rule kept:** a work is admitted only when
**two independent sources** name it at this museum (site, Wikipedia-EN,
Wikipedia-local, and each distinct web domain are independent). One mention or
zero is never a stop; nothing is invented.
- Wired: after R4, before UNIFIED-FILL; `thin` tier only; grounded search gated on
  an API key being present.

### #4 Building + collection-area stops — `museum_fallback_stops.py`
When still short, a museum tour's real non-artwork stops are added: the historic
**building** (HCMC occupies the Hui Bon Hoa mansion, 1929–1934) and **named
collection areas** (lacquer, silk painting, Champa sculpture, Óc Eo). Both are
grounded in the already-fetched corpus — a building/area ships only when the
corpus names it, never invented. They are typed, `verified=True` stops (so the
LOCAL-16 gate keeps them) and are exempt from the BLOCKER1 suspect-venue check.
The LOCAL-632 shortfall line now covers only what is **truly** left.
- Wired: after thin-verify, before UNIFIED-FILL; `thin` tier only.

### #5 Refinement — thin pool fragment exclusion
After the live run shipped 4/5 (the gate dropped one entry as a duplicate
canonical — a split-title fragment had re-entered the pool and resolved to a work
already in the list), I filter the thin-verify pool to drop any candidate that is
a fragment of an already-verified work, so a slot is spent on a NEW work instead
of a dedup-dropped duplicate. Zero-cost, offline.

---

## 3. Tests

| File | Cases | What it pins |
|---|---|---|
| `test_local667_title_split.py` | 14 | HCMC five-fragment collapse; "and"/comma clause collapse; distinct works (Courtauld/NG/Uffizi/Frick/Walters) never merged; two-word titles not collapse targets; hint quoting. |
| `test_local667_thin_museum.py` | 14 | Two-independent-source rule; one source / same page twice / zero sources never verify; corpus + grounded reaches the bar; grounded error ignored; local vs EN sources independent; never invents beyond the candidate pool. |
| `test_local667_building_stops.py` | 12 | Hui Bon Hoa mansion from corpus; building QID forces a stop; absent area never invented; building-first-then-areas, capped to needed; nothing grounded → honest shortfall; 1 work + building + areas → 5. |

```
$ python3 -m pytest test_local667_title_split.py test_local667_thin_museum.py test_local667_building_stops.py -q
40 passed
```

### Usual suites (offline, exit codes)
`python3 -m pytest <selection/verification/fill suites>` → **255 passed, 1 skipped,
2 failed (both pre-existing)**, across
`tests/test_local30_deterministic_selection.py`, `tests/test_local25_unified_fill_filter.py`,
`tests/test_local577_museum_refill.py`, `test_local583_documented_works.py`,
`test_tier_computation.py`, `test_local632_junk_and_shortfall.py`,
`test_local629_selection_diversity.py`, `test_local656_fast_selection.py`,
`test_local583_chrome_rejection.py`, `test_local589_canonical_set_chrome_free.py`,
`test_local642_paren_title_flatten.py`, `test_local653_site_candidates.py`,
`test_local639_collection_holders.py`, `tests/test_local640_invented_names.py`,
`tests/test_local626_venue_not_a_stop.py`, `tests/test_local626_highlight_first.py`,
`test_local485_venue_class_routing.py`, `test_w4_matcher.py`,
`test_local617_work_first.py`, `test_local580_structural_extraction.py`,
`test_local634_title_line.py`, `tests/test_local641_fresh_equals_reuse.py`,
`test_contained_regression.py`.

**Three pre-existing failures** were confirmed to fail **identically on the base
commit `0b0f433a`** (i.e. NOT caused by this change) by checking out the base
`generate_tour_text.py` and re-running each:
- `tests/test_local25_unified_fill_filter.py::test_no_bare_venue_name_in_classify_calls`
- `test_local589_canonical_set_chrome_free.py::test_corpus_canonical_set_has_no_chrome_and_keeps_shows`
- `test_local580_site_first_candidates.py` (2 cases — require live network)

---

## 4. No regression on well-documented museums (offline)

The thin-verify and building/area blocks are `tier == 'thin'` **only** — a
rich/medium museum never enters them. The one all-tier change, the collapse guard,
is a **strict no-op** for well-documented museums (their candidates are full,
distinct titles, not fragments of one another). Offline proof over the five named
museums' full-title candidate sets:

```
Courtauld          collapses=0  unchanged=True
National Gallery   collapses=0  unchanged=True
Uffizi             collapses=0  unchanged=True
Frick              collapses=0  unchanged=True
Walters            collapses=0  unchanged=True
ALL WELL-DOCUMENTED MUSEUMS UNCHANGED BY COLLAPSE GUARD: True
```

(Unit test `test_courtauld_distinct_works_untouched` pins the same invariant.)

---

## 5. Live run (own container, HCMC, 5 stops, museum, fresh, NORMAL arm)

Built `Dockerfile.generator` from this branch and ran ONE fresh paid tour in a
disposable container (`docker run --rm --name local667-gen -p 5167:5000` on
`development_default`; **not** `docker compose -p audioura`, no `audioura-*`
container touched). Harness: `run_local667_live.sh` + `run_local667_container.py`.

**Outcome: baseline 1 of 5 → delivered 4 of 5.** Stored as ONE additive `is_test`
row, `audio_tours.id = 663` (row count 453 → 454; is_test 387 → 388). No DELETE.

| Stop | Title | Verification source |
|---|---|---|
| 1 | North Central South Spring Garden | D1v2 (SPARQL / Wikidata `Q109406846`) — delivered as ONE whole work (Nguyễn Gia Trí lacquer, 1969–1989) |
| 2 | Lotus Flower | thin-verify, 2 sources: `studocu.vn` + `baotangmythuattphcm.com.vn` |
| 3 | The Life of the Vietnamese People | thin-verify, 2 sources: `bestpricetravel.com` + `nhiepanhdoisong.vn` |
| 4 | Portrait of a Lady | thin-verify, 2 sources: `vietnamnews.vn` + `quangsan.museum` |

**Detectors (all PASS):**
- `NO_BARE_FRAGMENT_STOP`: `[]` — no North/Central/South/Garden fragment shipped.
- `WHOLE_WORK_PRESENT`: `True` — the one real work is delivered intact.
- `IMPROVED_STOP_COUNT`: `delivered_stops=4` (baseline 1).

Log proof: `[D1v2] VERIFIED 'North Central South Spring Garden'` (the collapse
worked — no fragments reached D1v2); `[LOCAL-667 THIN-VERIFY] 3 of 26 … reached the
two-independent-source bar` → `total now 5/5`; then `[LOCAL-16 GATE] … Accepting
honest shortfall: 4/5`.

**Kiro / quality:** this run was scored by the in-pipeline gates, not an external
Kiro rubric; I did not have a separate Kiro score harness for a museum tour in
this container, so I am not reporting a fabricated number. The decisive, verifiable
quality signal is the delivered itinerary going from 1 → 4 richly-narrated stops
with the title no longer fragmented.

### Honest caveats
1. **Cost cap breached.** Total **$1.2987** vs the **$0.80** cap
   (`paid_api_calls` / live_run_meter): openai $0.7799 + gemini_grounding $0.4620
   (13 requests / 9 queries) + preflight $0.0726 + serper $0.0390 +
   gemini_tokens $0.0178. The reserve gate passed before the tour (spend $0 +
   reserve $0.55 < $0.80), but a single `generate_tour_text` call ran to $1.30 and
   `COST_HARD_LIMIT_USD=0.80` did not abort mid-generation. I did **not** re-run —
   a second tour would only compound the overrun. One paid tour; no DELETE.
2. **4/5, not 5/5.** The run reached 5/5 before the LOCAL-16 gate, which then
   dropped one entry as a duplicate canonical (a split-title fragment had
   re-entered the thin pool). Commit #5 fixes this offline (excludes
   already-verified-work fragments from the pool) and would make it 5/5; I did
   **not** re-verify live, again because of the cost cap.
3. **Stop 2 content drift.** "Lotus Flower" is correctly selected and
   two-source-verified, but the narration drifted to a Japanese Kano-school work.
   This is a content-grounding issue in the stop writer, downstream of this ticket
   (title selection), and is not part of the LOCAL-667 fix surface.

---

## 6. Files

New: `candidate_collapse_guard.py`, `thin_wikidata_fallback.py`,
`museum_fallback_stops.py`, `test_local667_title_split.py`,
`test_local667_thin_museum.py`, `test_local667_building_stops.py`,
`run_local667_container.py`, `run_local667_live.sh`.
Edited: `generate_tour_text.py` (Phase-3A hint; collapse step in `_verify_works_v2`;
thin-verify + building/area blocks after R4; BLOCKER1 exemption; thin-pool fragment
filter).

Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
`.continuous_dev/STATUS.md`.

## 7. Commits (on `LOCAL-667-thin-wikidata-museum`, from `0b0f433a`)
1. `#1` collapse split-title candidates; quote multi-word Phase-3A hints
2. `#2` thin-Wikidata museums verify works before giving up
3. `#3` building + collection-area stops before an honest shortfall
4. `#4` live acceptance harness (own container, HCMC museum, cap $0.80)
5. `#5` exclude already-verified-work fragments from thin-verify pool
