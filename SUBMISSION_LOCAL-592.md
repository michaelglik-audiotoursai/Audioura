# SUBMISSION — LOCAL-592

**Exactly N stops: the museum "About" content and the practical facts are the OPENING SECTION of Stop 1, never an extra stop.**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-592-about-in-stop1`
- **Base:** subscribed @ `c9d4c47` (verified: `git merge-base --is-ancestor c9d4c47 HEAD` exits 0)
- **Commits:**
  - `aeffdbb` — RED tests (`test_local592_about_in_stop1.py`), failing on `c9d4c47`
  - `5690e21` — implementation (GREEN) + updated the 4 LOCAL-585 tests that encoded the superseded extra-stop behaviour
  - `1898abf` — isolated live-run harness (`run_local592_live.py` / `.sh`)

---

## 1. Michael's rule (2026-10-06, binding)

> "If a user asks for x number of stops, we are supposed to generate exactly x number of
> stops. In Walking tours we have the Overall section and that section is the start of
> Stop 1. The stop itself is after this section but still part of Stop 1. The same must be
> true with museum, restaurant, etc. and other tours. It is very important to say when the
> museum opens, how much they charge for entrance, etc. but it has to be the first section
> of Stop 1."

## 2. The problem on `c9d4c47`

LOCAL-585 (subscribed) adds "About &lt;museum&gt;" as an **EXTRA stop**: a 5-stop request
for the Boston Athenaeum delivered **6**, a 7-stop Griffin request delivered **8**. The
extra stop came from three places:

- `about_museum_stop.should_count_toward_n` — a count branch that treated About as a stop;
- `stop_pool_assembly.assemble_building_tour` — `about_lead = [about_stop]` prepended a
  standalone Stop 1;
- `stop_pool_orchestrator` — all three delivery paths built an About *stop unit*.

The walking tour already does the right thing: its `[R2]` prolog is **folded into Stop 1**
(it rides on the Stop-1 Orientation prefix — `generate_tour_text.py:~21407`,
`_saved_prolog`), "no standalone Introduction block". LOCAL-592 makes museum/facility/
building tours mirror that pattern.

## 3. What was delivered

### a. `about_museum_stop.py`
- **`should_count_toward_n(...)` now always returns `False`.** The About content is a
  SECTION of Stop 1, not a stop, so it can never add to or subtract from N. The LOCAL-585
  "thin exhibitions → count it" branch is gone. Kept as always-False so existing imports
  keep working and a request for N always delivers N.
- **`AboutStop.practical_facts`** field + **`build_about_stop(..., practical_facts="")`**
  parameter: an already-gated practical-facts string (hours / admission / closed days) is
  carried verbatim onto the AboutStop. Nothing is invented here — the sourcing + LOCAL-584
  gate are upstream.
- **`build_opening_section(about) -> str`**: composes the Stop-1 opening section —
  the sourced, artwork-framing-free About narration, then
  `"Before you go in, a few practical notes. <gated facts>"`. Empty when there is no story;
  practical-facts-only when the About narration would be unsafe (belt-and-braces artwork
  guard). This is the single block the caller folds into Stop 1.

### b. `stop_pool_assembly.py` — `assemble_building_tour`
- New `opening_section: str = ""` parameter. `ordered = new_stops + pooled_stops`
  (**no `about_lead`**). The opening section is folded into **Stop 1's narration opening**
  (the museum's story + practical facts come first, then Stop 1's own exhibition narration).
- The legacy `about_stop` unit is still accepted but is **folded**, never placed as its own
  stop — no caller path can resurrect an extra "About …" stop.
- `about_stops` is reported as `1` when an opening section was folded (for the ledger) but
  **adds ZERO stops**: `len(order) == len(new_stops) + len(pooled_stops)`.
- Pooled narration is still reused verbatim; `overall_orientation` still rides on Stop-1
  Orientation (LOCAL-590 unchanged).

### c. `stop_pool_orchestrator.py`
- `_build_about_stop_unit` → **`_build_opening_section`** (returns the opening-section text).
- **`_source_practical_facts(venue, site_url, address)`**: fetches the venue's visit/hours/
  admission pages, extracts with `visitor_facts_extractor` (venue-bound hours), and runs the
  result through `practical_facts_gate.gate_formatted_facts` (the ONE LOCAL-584 gate:
  venue-bound, dated, state-only-what-the-page-supports). Best-effort — any failure yields
  `""` and the opening section carries only the About story (silence is correct, D584).
- All three delivery paths (K==0 first tour; N≤K; N>K) now request **exactly N** exhibition
  stops and pass `opening_section=` instead of `about_stop=`.

### d. Restaurant / outdoor tours — unchanged (D538)
`assemble_outdoor_tour` is untouched: the walking Overall section already folds into Stop 1,
and each restaurant's practical facts stay in that restaurant's stop. Only single-venue
(museum / facility / contained building) tours gained the fold.

## 4. Tests

New: `test_local592_about_in_stop1.py` (16 tests) — **RED on `c9d4c47`, GREEN after**:
- `should_count_toward_n` is always False (the About content never consumes/adds a stop);
- the opening section carries both the About story and the practical facts, artwork-framing-free;
- Athenaeum **5 → 5** and Griffin **7 → 7**: Stop 1 opens with the About + practical section,
  then the first artwork's own narration, in the same stop;
- no stop is titled "About …";
- pooled bodies stay verbatim; the opening section is regenerated per tour;
- backward compatible when no opening section is supplied.

Updated the 4 LOCAL-585 tests that encoded the now-superseded extra-stop behaviour
(`should_count_toward_n`, counts-when-thin, and the "About is Stop 1" assembly class →
"About is folded into Stop 1").

**Suite exits (all 0):**

```
exit=0 test_local592_about_in_stop1
exit=0 test_local584_venue_bound_hours
exit=0 test_local584_practical_facts_currency
exit=0 test_local585_about_museum_stop
exit=0 test_local585_r2_about_hygiene
exit=0 test_local590_assembly
exit=0 test_local590_pool_store
exit=0 test_local590_orchestrator
exit=0 test_local591_verdict_equals_reasoning
exit=0 test_local591_contained_venue
exit=0 test_local591_one_scope_per_tour
exit=0 test_local591_every_stop_has_coordinates
```

Combined run: **153 passed**. LOCAL-582 / 589 also green (29 passed) — no regression.

## 5. Live, ISOLATED run

`./run_local592_live.sh` — a DISPOSABLE `local592-gen-img` container (`docker run --rm`,
name `local592-gen-…`), on `development_default`, with its OWN `--env-file` (the project
`.env`, i.e. the env the `audioura-tour-generator-1` container uses). Never an `audioura-*`
container; the image is removed at the end; `audio_tours` is only counted (202 → 202, never
written/deleted). OpenAI hard cap `$1.00` (&lt; the $2 ticket cap), tour cache OFF.

### CASE ATHENAEUM — "Art and Architectual tour in Boston Athenaeum, boston, ma" (5 requested)

**Delivered EXACTLY 5 stops. No stop titled "About …".**

```
Stop 1: Boys Come Over Here You're Wanted
Stop 2: Picture Gallery with Views of Modern Rome
Stop 3: Landscape with Cottages and Pond
Stop 4: Cutter Expansive Classification
Stop 5: Annie Adams Fields
```

Stop 1 — first 15 lines (About + architecture opening section, then the first artwork):

```
Stop 1: Boys Come Over Here You're Wanted
Address: 10 1/2 Beacon St, Boston, MA 02108
Coordinates: 42.3584, -71.0637
Orientation: You are about to explore the Boston Athenaeum in Boston. … Your first stop is Boys Come Over Here You're Wanted.
Before we look at anything on the walls, here is the story of Boston Athenæum in Boston,
Massachusetts itself — who created it, why it exists, and what it is known for. The Boston
Athenæum is one of the oldest independent libraries in the United States. … The institution
was founded in 1807 by the Anthology Club of Boston. … Construction on the Athenaeum's present
home on Beacon Street began in 1847. Designed by Edward Clarke Cabot, the building opened in
1849 … A word about the building you are standing in. … This account is drawn from the museum's
own pages on bostonathenaeum.org and public reference sources.
The poster "Boys Come Over Here You're Wanted" was a centerpiece in the 2014 exhibition …
```

### CASE GRIFFIN — "Griffin museum of photography, Winchester, MA" (museum, 7 requested)

**Delivered EXACTLY 7 stops. No stop titled "About …".**

```
Stop 1: BU Masters Show 2026 | Traces: Pursuing Process
Stop 2: Intertidal : Field Notes
Stop 3: Earth, Wind & Fire
Stop 4: Tabitha Soren | An Artist Life
Stop 5: TLC
Stop 6: Lua Kobayashi |The Persistence of Memories
Stop 7: Homage | Robert Frank: The Americans
```

Stop 1 opens with the About section (then the first exhibition's own narration):

```
… Before we look at anything on the walls, here is the story of Griffin Museum of Photography
in Winchester, Massachusetts itself — who created it, why it exists, and what it is known for.
Arthur Griffin was an American photographer. … The Griffin Museum of Photography is a 501(c)3
nonprofit organization dedicated to the art of photography. … Founded in 1992 as a private
foundation, the Griffin Museum of Photography became a nonprofit public charity in 2000. This
account is drawn from the museum's own pages on griffinmuseum.org and public reference sources.
```

Both ran through the LOCAL-590 pool fast-path (pool held 5 / 7): `reused=5/7, new=0,
about_stops=1` — the `about_stops=1` is the **folded opening section**, adding **zero** stops.

### Practical facts on the live run (honesty contract held)

Both live runs logged `practical_facts=none`. This is the **LOCAL-584 gate working as
designed**, not a wiring gap: the live pages' extracted spans (`'81–72'`, `'20–76'`,
`'Free for Métropole residents'`) were **dropped** because they are not literally supported by
the fetched page — silence over a guess (D584). The wiring is proven to surface *real* facts:
on the committed fixture `tests/fixtures/griffin_about_2026.html`,
`stop_pool_orchestrator._source_practical_facts(...)` returns
`'Closed on Monday. Noon–4 PM. $12'`, and `build_opening_section` folds
`"Before you go in, a few practical notes. Closed on Monday. Noon–4 PM. $12."` into Stop 1 —
exactly as the LOCAL-584 suite asserts.

(The harness's `non_artwork=False` flag on Griffin is a false positive of the audit heuristic:
it scans the *whole* of Stop 1, including the exhibition body — which legitimately says
"The work titled 'Interference' …". The About *opening section* itself is artwork-framing-free,
as the unit tests assert.)

## 6. Process

- No GCloud.
- Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
  .continuous_dev/STATUS.md.
- Committed + pushed after each step; `git rev-list --count subscribed..HEAD` ≥ 1 throughout.
- Branch created from HEAD (`c9d4c47`), never from `origin/*`.
