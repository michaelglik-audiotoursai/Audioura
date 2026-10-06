# SUBMISSION — LOCAL-585

**Museum tours open with the museum's own story (founder, history), not a web page disguised as an artwork.**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-585-museum-story-stop`
- **Base:** subscribed @ `94dbe48` (verified: `git merge-base --is-ancestor 94dbe48 HEAD` exits 0)
- **Commits:**
  - `e49f31d` — About-stop module + assembly wiring + unit tests
  - `79acab2` — Athenaeum contained-request fix + isolated live-run drivers + evidence

---

## 1. The problem (Michael, tour 391 + Athenaeum)

Tour 391's first stop had the right *content* — the Griffin's history (Arthur Griffin,
the founding board, founded as a private foundation in 1992, a non-profit public
charity since 2000). But it was delivered as an **artwork**:

> "Griffin Museum Board Of Directors 2 **consists of a series of frames** …"

That framing is invented: a page about the institution is not a work on the wall.
LOCAL-583/589 already **reject** that chrome title from the artwork/exhibition set.
LOCAL-585 is the **positive mirror** — the same founding content *should* be delivered,
as a proper **"About <museum>"** story stop, sourced like any stop, never as an artwork.

Separately (Athenaeum, 2026-10-06): "Art and Architecture tour in Boston Athenaeum"
delivers 5 artworks inside the building (LOCAL-591) but **no stop about the building
itself**. The About stop must cover the venue's architecture and history when the
request names architecture or the building is architecturally notable — sourced.

---

## 2. What was delivered

### a. New module `about_museum_stop.py`
`build_about_stop(...) -> AboutStop | None` builds one **"About <museum>"** story stop:

- **Sourced from the venue's OWN pages** (About / history / mission / "the-building"
  seeds) and, when available, **Wikipedia/Wikidata** (`default_wiki_provider`, a
  dependency-light Wikipedia REST summary; architecture notability inferred). Every
  network touch is injectable (`fetcher`, `wiki_provider`) so the stop builds from
  fixtures with no HTTP — the same honesty contract as `museum_overview.py` / D538.
- **Never framed as an artwork.** `looks_like_artwork_framing()` rejects object-label
  language ("consists of a series of frames", "this work", "oil on canvas", "the artist
  depicts…"). If the composed narration drifts into that framing it is recomposed, and
  if it still cannot be made safe the stop is dropped.
- **No artwork fields.** `about_stop_unit()` emits a plain dict with `title="About
  <museum>"`, `_about_stop=True`, `_pool_reused=False`, and **no** `artist` / `year` /
  `type_specialty` / `specific_examples` — the fields that make a block read as a work.
- **Architecture coverage** (`request_wants_architecture()`, incl. the real field-request
  misspelling "architectual") fires when the request names architecture **or** the
  building is architecturally notable; it adds a sourced "who designed it / when / what
  style" section.
- **Count semantics** (`should_count_toward_n()`): the About stop counts toward the
  requested N **only** when exhibition material is too thin to reach N on its own;
  otherwise it is a free, enriched opener in front of the full N exhibition stops.
- **Never invents.** If neither the venue's pages nor the wiki sources yield a story,
  `build_about_stop` returns `None` and the tour is unchanged (D577).

### b. `stop_pool_assembly.assemble_building_tour`
Gained an optional `about_stop` parameter placed **FIRST** (Stop 1), before new and
pooled exhibition stops. `AssemblyResult.about_stops` reports it. Fully backward
compatible — omitting the param reproduces the pre-LOCAL-585 order.

### c. `stop_pool_orchestrator`
- `_build_about_stop_unit()` resolves the venue's own site (`venue_resolver`, best-effort,
  non-fatal), keys on the **building** name for themed-in-building requests
  (`clean_venue_request_name`), and wires `default_wiki_provider`.
- Wired into the **N≤K** and **N>K** building branches, and a new **K==0 first-tour**
  branch (empty pool): generate the N exhibition stops normally — so every
  existence/scope/dedup gate runs — then re-assemble with the About stop leading;
  the exhibition stops seed the pool.
- `_looks_contained_request()` / `_classify()` promote a themed-in-building request
  (interior preposition + institutional tail noun, e.g. the Athenaeum) to a **museum**
  tour so the About stop can lead it — the shallow pre-Phase-1 classifier called it
  "walking".
- `DISABLE_ABOUT_STOP=1` opt-out.

### d. `generate_tour_text.py`
Pool-delivery cost breakdown + log line carry `about_stops`.

---

## 3. Tests (`test_local585_about_museum_stop.py` — 23 passing, offline)

- Griffin founding story surfaces (**Arthur Griffin**, **1992**, **non-profit**).
- **Never** framed as an artwork; no `consists of a series of frames` / `this work` / `oil on canvas`.
- Sourced to the venue domain; cruft (newsletter opt-in) is not lifted.
- The stop unit carries **no** artist/year/type_specialty/specific_examples.
- Count semantics: not-count when exhibitions plenty; count when thin.
- Architecture coverage fires on an architecture-named request **and** on a wiki
  notability flag; stays off for a plain art request at a non-notable venue.
- No story → `None` (never invent).
- Pure predicates (`request_wants_architecture` incl. the "architectual" typo,
  `looks_like_artwork_framing`, `should_count_toward_n`, `clean_venue_request_name`).
- Assembly places the About stop **first** (Stop 1), reuses pooled narration verbatim,
  renders no artwork fields, and is backward compatible without the param.

**Regression suite:** 187 passing across LOCAL-585 + 590 (assembly/orchestrator/pool_store)
+ 582 + 583 + 589 (×5) + 591 (×4) + 584 (×2). The 6 failures in
`test_local480_facility_category.py` are **pre-existing on base `94dbe48`** (proven by
running the base `generate_tour_text.py`: the same 6 fail) — a test that greps the thin
`generate_tour_text` wrapper's source for strings that live in `_generate_tour_text_impl`.
Not caused by LOCAL-585; out of scope.

---

## 4. Isolated live run (never `audioura-*`; OpenAI cap $2)

`./run_local585_live.sh` builds `Dockerfile.generator` and runs ONE disposable
container `local585-gen-*` with `docker run --rm`, `--network development_default`
(so the stop-pool DB `postgres-2` resolves), its **own** `--env-file` (the project
`.env`, i.e. the env the `audioura-tour-generator-1` container uses),
`STORIED_MODE=true`, `DISABLE_TOUR_CACHE=1`, `COST_HARD_LIMIT_USD=2.00`. `audio_tours`
is only counted, never written or deleted. Evidence: `tours/local585_live/`.

### GRIFFIN — `Griffin museum of photography, Winchester, MA` (7 requested → 8 delivered)
- **Stop 1 = "About Griffin museum of photography"** — names the founder **Arthur
  Griffin**, "501(c)3 nonprofit", "**Founded in 1992** … became a nonprofit public
  charity in 2000", the mission; **sourced to griffinmuseum.org**; **not** framed as an
  artwork; `consists of a series of frames` absent from the whole tour.
- Stops 2–8 = current exhibitions (BU Masters Show 2026, Intertidal, Earth Wind & Fire,
  Tabitha Soren, TLC, Lua Kobayashi, Robert Frank).
- `about_stops=1`, cost **$0.00** (pool reuse).

### ATHENAEUM — `Art and Architectual tour in Boston Athenaeum, boston, ma` (5 → 6)
- **Stop 1 = "About Boston Athenaeum"** — "founded in **1807** by the Anthology Club",
  **plus an architecture section**: "Designed by **Edward Clarke Cabot**, the building
  opened in **1849**, with a sculpture gallery on the first floor, the book collection on
  the second, and a painting gallery on the skylit third floor." `covers_architecture=True`;
  non-artwork; sourced.
- Stops 2–6 = the 5 artworks inside the building.
- `about_stops=1`, cost **$0.00** (pool reuse).

Both runs stayed far under the $2 cap (pool-served from prior 589/590 seeding, which
exercises the N>K branch). The empty-pool first-tour case is covered by the K==0
contained branch and by the unit tests.

---

## 5. Process

- Branched from HEAD at base `94dbe48`; verified ancestry before every commit.
- Commit + push after each step (implementation; then live-run + evidence).
- Did not edit DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / STATUS.
- Never deleted anything; never touched `audioura-*` services.

## 6. Files

- `about_museum_stop.py` (new)
- `stop_pool_assembly.py` (About-stop param, placed first)
- `stop_pool_orchestrator.py` (About-stop wiring + contained-request promotion)
- `generate_tour_text.py` (about_stops in the pool-delivery cost record)
- `test_local585_about_museum_stop.py` (new, 23 tests)
- `run_local585_live.py`, `run_local585_live.sh` (new, isolated live run)
- `tours/local585_live/` (live evidence)
