# SUBMISSION — LOCAL-744: screen-work tours, honestly

**Branch:** `LOCAL-744-screen-work-tours`
**code_sha:** `2659c2e954f9544eb5f0c6dd8bde09c9338baf36`
**Base:** `3e2e7d84` (the LOCAL-743 merge — this ticket was PARKED until LOCAL-743
landed in `subscribed`; `git merge-base --is-ancestor 3e2e7d84 HEAD` → exit 0).

> Base note: the generic BASE header named `fc36b842` as "subscribed". On this
> worktree `fc36b842` is the **LOCAL-746** merge commit (a different, later
> ticket) and is **not** an ancestor of this branch. The ticket's own
> LOCAL-744 section says to branch from "`subscribed` @ 3e2e7d84 or later — it
> contains LOCAL-743", which is the authoritative, task-specific base and is
> satisfied. I did not branch from `origin/*`.

---

## What Michael asked for
"The episode 1 of season 1 biking tour, Salem, MA" is WGN's *Salem* (2014), S1E1.
The generator ignored "episode 1 of season 1" and shipped a generic Salem bike
tour. The show was filmed in Shreveport, Louisiana, so no Salem place appears on
screen — and the tour never said so. Michael's priority (11:3x): **"The tour will
say so when the show was filmed elsewhere — this is the most important part,"**
keep the good real Salem stops, and **never guess** the filming location.

## What changed
1. **Intent** — `screen_work_tour.detect_screen_work` recognises a screen/book
   work, including the title-less "episode 1 of season 1 …" case (a season/episode
   reference forces `theme_type = TV`). A plain place request ("Salem, MA biking
   tour") matches nothing → no disclosure, no false positive.
2. **Honest, sourced Orientation opening** — `build_filming_disclosure` emits one
   of three sentences: filmed-elsewhere / filmed-here / could-not-confirm. A claim
   ships **only with a source**; otherwise it says "we could not confirm where it
   was filmed". `inject_orientation_disclosure` splices it as the first sentence of
   the Orientation (idempotent). It is computed in `_generate_tour_text_impl` and
   spliced at the single every-path delivery choke point
   (`_apply_delivery_hours_guard`), so it ships on fresh/cache/pool paths alike.
3. **Sourced filming lookup (`generate_tour_text.filming_location_lookup`)** — the
   model identifies the **work**; the filming **place is derived directly from the
   work's Wikipedia article** (`_filming_place_from_article`, a directional
   "filmed/shot … in &lt;Place&gt;" match), trying kind-qualified disambiguations
   ("Salem" → "Salem (TV series)"). The place comes from the source itself, not a
   model guess. If no article place and no corroborated model place → "could not
   confirm". Fail-closed, never-guess.
4. **Existence gate keeps real outdoor-tour places** (`stop_existence_gate.py`) —
   the robust Wikidata-P625/OSM existence check was reached only for
   `('walking','specialized')`; a **biking** tour (716) skipped it, so real Salem
   places were dropped as "no evidence". `_WALKING_KINDS` now also admits
   biking/cycling/driving/animal/country_scale, and a generic metro-radius (35 km)
   coordinate fallback (`_within_metro_744`) was added to the geographic tier-1
   check (previously Riviera-bbox only).

Files: `screen_work_tour.py` (new), `generate_tour_text.py` (additive),
`stop_existence_gate.py`, `test_local744_screen_work_disclosure.py` (new),
`run_local744_container.py` / `run_local744_live.sh` / `run_local744_verify_salem.py`
(live harness).

---

## Tests — `test_local744_screen_work_disclosure.py` (24 passed)
`python3 -m pytest test_local744_screen_work_disclosure.py -q` → **24 passed**.

**Red → green proof (genuinely red at baseline 3e2e7d84):**
- Disclosure tests depend on `screen_work_tour.py`, which **did not exist** at
  baseline.
- `test_raw_716_has_no_filming_disclosure_today` asserts the delivered 716 text
  (fixture) has NO "filmed in" / "none of these places appears on screen" — the
  defect; `test_orientation_opens_with_sourced_disclosure_after_fix` asserts the
  Orientation then LEADS with the sourced sentence.
- Existence-gate: baseline `stop_existence_gate.py` has
  `_WALKING_KINDS = ('walking','specialized')` (no biking) and **zero**
  occurrences of `_within_metro_744` — so `test_biking_reaches_the_walking_existence_fallback`
  and `test_geographic_tier1_has_generic_metro_fallback` fail at baseline.

Covered: intent detection incl. the title-less case; filmed-elsewhere; filmed-here;
unsourced → "could not confirm"; unknown/ crashing lookup → "could not confirm";
plain place → no disclosure; the real Salem stops untouched by the splice;
article-derivation (extract Shreveport, setting-only yields none, full lookup
prefers the article over the model's guess, bare-title disambiguation tries
"(TV series)"); and a network-gated check that verifies the three real Salem
places via Wikidata/OSM.

**Existence-gate investigation (requirement 4) — the three dropped 716 places are
verified live:**
```
[LOCAL-744] VERIFIED 'Pickering Wharf'          — nominatim_osm: 'Pickering Wharf' in salem [building/mixed_use]
[LOCAL-744] VERIFIED 'Winter Island Park'       — nominatim_osm: 'Winter Island Maritime Park' in salem [leisure/park]
[LOCAL-744] VERIFIED 'Fort Pickering Lighthouse'— nominatim_osm: 'Fort Pickering Light' in salem [man_made/lighthouse]
```
Cause: they are real Salem places, but a biking tour never reached the robust
existence check (tour kind not in `_WALKING_KINDS`) and had no coordinate fallback
outside the Riviera bbox — now fixed.

**No regressions vs baseline:** offline/deterministic generator suites —
`test_local46_transport_scope`, `test_local485_venue_class_routing`,
`test_local591_every_stop_has_coordinates`, `test_local591_one_scope_per_tour`,
`test_local617_work_first`, `test_local627_signature_first`, `test_tier_computation`,
`test_local722_duplicate_work` → **107 passed**. `test_local480_facility_category`
→ 90 passed, **6 failed (TestWiring only)**; these 6 are **pre-existing/stale**,
not a regression — they `inspect.getsource(generate_tour_text)` (the public
wrapper) for strings that live in `_generate_tour_text_impl` (the wrapper/impl
split predates LOCAL-744). Proven by swapping the **baseline** `generate_tour_text.py`
into the worktree and re-running `TestWiring` → identical **6 failed, 1 passed**.
My diff touches none of those facility-wiring strings.

---

## Live runs — own disposable containers only
Container `local744-*` (`--rm`), spare published ports 5144/5145/5146, image built
from the branch tree and removed after. Network `development_default`, DB
`development-postgres-2-1` / `audiotours`. **Never** `-p audioura`, never touched
`audioura-*`. Tour cache OFF, stop pool OFF (fresh), existence gate `enforce`.
Rows stored **additive** `is_test=true` with **lat/lng NULL**. **No
`DELETE FROM audio_tours`** (D141).

### SALEM — "the episode 1 of season 1 biking tour, Salem, MA" (5 stops, biking) — id 732
**Orientation opening (verbatim):**
> The TV series Salem was filmed in Shreveport, Louisiana, not in Salem, so none
> of these places appears on screen. This tour visits the real Salem, where the
> story is set.

Source: *Salem (TV series) — Wikipedia* ("It was filmed in Shreveport, Louisiana…").
Stops (real places the 1692 story is set): Salem Maritime National Historic Site,
Derby Wharf, The House of the Seven Gables, Salem Common, The Witch House. The good
real places were kept; the honest framing was added — exactly Michael's ask.
Cost this run $0.246.

### SHREVEPORT — "the episode 1 of season 1 tour, Shreveport, Louisiana" (5 stops) — id 730
**Orientation opening (verbatim):**
> We could not confirm where this TV series was filmed. The Strand Theatre,
> designed by architect Emile Weil and once dubbed the "Million-Dollar Theatre,"
> opened its doors as a vaudeville venue and quickly became a cultural cornerstone
> in Shreveport.

Honest outcome: for a bare "episode 1 of season 1, Shreveport" the model
identified the work as *True Blood*, which the work's Wikipedia article did not
corroborate as filmed there, so the system **refused to guess** and said so —
exactly the never-guess rule. Stops are real Shreveport places (The Strand
Theatre, Shreveport Municipal Auditorium, Caddo Parish Courthouse, The Robinson
Film Center, The Shreveport Times Building). Cost this run $0.375 (the two-arm run
total was $0.544).

### Row counts (audio_tours, DB `audiotours`)
| point | total | is_test |
|---|---|---|
| before first run | 506 | 430 |
| after two-arm run (729 Salem, 730 Shreveport) | 508 | 432 |
| after Salem verify (731) | 509 | 433 |
| after final Salem delivery (732) | 510 | 434 |

Net: **+4 additive `is_test` rows**, lat/lng NULL, no deletes.

### Budget
Per-run spend, measured from `paid_api_calls` relative to a baseline captured at
container start:
- two-arm run (Salem+Shreveport): **$0.544**
- Salem verify run: **$0.242**
- final Salem delivery run: **$0.246**
- direct cheap lookup verification (one short model call per arm): **~$0.002**

Each individual run was well under the $1.00 cap (hard-capped in-container). The
work needed a second and third Salem run to confirm the article-derivation fix
after the first run exposed the model's wrong-place guess, so the **session total
≈ $1.03** — marginally over the $1.00 single-run budget. Flagging this
transparently rather than hiding it; the fix and its live confirmation required
the extra short runs.

---

## Honesty note on the two arms
The headline case (Salem) now delivers the exact sourced disclosure Michael
wanted. The Shreveport arm correctly returns "could not confirm" because the model
mis-identifies which specific work "episode 1 of season 1, Shreveport" refers to
(Shreveport has hosted many productions) and the fail-closed corroboration refuses
an uncorroborated place. That is the intended behaviour — **never a guess** — not a
silent wrong claim. Improving work-identification for an ambiguous place-only
request is a candidate follow-up.
