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


---

## r2 — About-stop listener-facing defects (LEAD review, 2026-10-06)

The design was accepted; `tours/local585_live/LOCAL585_ATHENAEUM.txt` stop 1 shipped
four listener-facing defects. All four are now fixed, with tests red on `5a2b4bd` and
green after, and re-verified by an isolated live run.

- **Branch/base:** `LOCAL-585-museum-story-stop`, continued at HEAD `5a2b4bd`
  (`git merge-base --is-ancestor 5a2b4bd HEAD` exits 0).
- **r2 commit:** `a46ab59` — the four fixes + `test_local585_r2_about_hygiene.py`.

### The four defects and the fix

1. **Truncated sentence** — shipped "…a group of Bostonians who produced a magazine
   **called.**" (object cut). A sentence whose final content token still expects an
   object (`called`/`named`/`titled`/`known as`/`such as`/`including`/`designed by`/
   a bare trailing `and`/`the`/…) is now DROPPED, never spoken. New pure predicate
   `has_dangling_object_sentence()`; applied where story and architecture sentences
   are collected (`_is_story_sentence`, `_collect_architecture_sentences`) and inside
   `dedupe_sentences`.
2. **Duplicate sentence** — "Designed by Edward Clarke Cabot, the building opened in
   1849, with a sculpture gallery…" appeared **twice** (once in the history, once in
   the "A word about the building…" section). `_compose_about_narration` now builds
   the body as ONE de-duplicated pool (`dedupe_sentences` over wiki+story) and filters
   the architecture section against it, so a sentence shared across sections is spoken
   **once**. Normalised comparison via `_dedup_key`.
3. **Raw request locality in narration** — "here is the story of Boston Athenaeum in
   **boston, ma** itself". `normalise_locality()` properly-cases the tail and expands
   US state codes ("boston, ma" → "**Boston, Massachusetts**"); the orchestrator reads
   the resolver's display name (`VenueEntity.name`, which the old `getattr(.., "venue_name")`
   never found) for the venue.
4. **Raw request string in Directions** — "Continue through **Art and Architectual tour
   in Boston Athenaeum** — next is…". Fixed on BOTH transition composers:
   `stop_pool_assembly._museum_transition` now cleans the venue via a new `_venue_name`
   helper (`clean_venue_request_name`), and `generate_tour_text` cleans
   `_museum_venue_name` immediately after intent — before it is woven into
   "Continue through {venue} — next is …" or the single-venue constraint.

### Tests (`test_local585_r2_about_hygiene.py` — 10, offline)

Pins the EXACT Athenaeum strings: no dangling "produced a magazine called."; the
architect sentence appears exactly once; the lowercase request locality is absent and
"Boston, Massachusetts" present; the pool-assembly transition and the generator's
venue derivation both name the venue, not the raw request. Plus pure-predicate tests
for `has_dangling_object_sentence`, `dedupe_sentences`, `normalise_locality`.
Red on `5a2b4bd` (9/10 failed before the fix), green after. The 23 original LOCAL-585
tests still pass; **137 passed** across the touched-module suite (585 r2 + 585 + 590
assembly + 591 contained-venue/one-scope/verdict + d523 story hygiene + local44 + local494).

### Isolated live run (disposable container `local585-gen-img`, never `audioura-*`; OpenAI cap $1)

`./run_local585_live.sh` — `docker run --rm`, `--network development_default`
(so `postgres-2` resolves), own `--env-file`, cache OFF, `COST_HARD_LIMIT_USD=1.00`.
Both cases pool-served, cost **$0.00**. The disposable image is removed at the end;
`audio_tours` only counted, never written/deleted; no `audioura-*` service touched.
r2 audit flags all green for both: `no_dangling`, `no_dup`, `no_raw_locality`,
`no_dir_raw`.

**ATHENAEUM** `Art and Architectual tour in Boston Athenaeum, boston, ma` (5 → 6):

> Stop 1 (About Boston Athenæum): "Before we look at anything on the walls, here is the
> story of Boston Athenæum in **Boston, Massachusetts** itself … The institution was
> founded in 1807 by the Anthology Club of Boston, Massachusetts … **Designed by Edward
> Clarke Cabot, the building opened in 1849, with a sculpture gallery on the first
> floor, the book collection on the second, and a painting gallery on the skylit third
> floor.** [appears once] … A word about the building you are standing in. …"
> (the truncated "produced a magazine called." sentence is **gone**.)
>
> - Directions: `Continue through Boston Athenaeum — next is Boys Come Over Here You're Wanted.`
> - Directions: `Next: Picture Gallery with Views of Modern Rome.`

**GRIFFIN** `Griffin museum of photography, Winchester, MA` (7 → 8):

> Stop 1 (About Griffin Museum of Photography): "… here is the story of Griffin Museum
> of Photography in **Winchester, Massachusetts** itself … Arthur Griffin was an American
> photographer … a 501(c)3 nonprofit organization … **Founded in 1992** as a private
> foundation, the Griffin Museum of Photography became a nonprofit public charity in 2000."
>
> - Directions: `Continue through Griffin museum of photography — next is BU Masters Show 2026 | Traces: Pursuing Process.`
> - Directions: `Next: Intertidal : Field Notes.`

### Files (r2)

- `about_museum_stop.py` — `has_dangling_object_sentence`, `dedupe_sentences`,
  `normalise_locality` (+ `_hygiene_split`, `_dedup_key`, `_titlecase_place`); hygiene
  wired into collection and `_compose_about_narration`.
- `stop_pool_assembly.py` — `_venue_name` helper; `_museum_transition` cleans the venue.
- `generate_tour_text.py` — cleans `_museum_venue_name` before seams/constraint.
- `stop_pool_orchestrator.py` — About-stop unit reads the resolver display name.
- `test_local585_r2_about_hygiene.py` (new, 10 tests).
- `run_local585_live.py` / `run_local585_live.sh` — r2 hygiene audit, full Stop-1 +
  Directions dump, cap $1, disposable image renamed off `audioura-*`.
