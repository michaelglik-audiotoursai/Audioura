# SUBMISSION — LOCAL-528: airport-origin stories bolted onto a jetbridge

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-528-content-assigned-to-wrong-structure
**Base:** storied = `1a98917` (verified `git merge-base --is-ancestor 1a98917 HEAD` → exit 0)

## The defect

A jetbridge is a boarding bridge attached to a gate. Jet bridges did not exist
until 1958–59, yet the LOGAN tours put pre-jetbridge material on the jetbridge stop:

- **LOGAN_1 stop 3 (Jetbridge)** — the 1927 Charles Lindbergh landing. Round 8, on
  the current tree with every fix merged, still carries it, and the SAME stop dates
  Massport correctly: *"The Massachusetts Port Authority, established in 1959,
  operates Logan…"* An impossible 1927 date and a correct 1959 date side by side,
  and nothing noticed. (Verified in `TOURS_FOR_REVIEW/round8/LOGAN_1.txt` and
  `round7/LOGAN_1.txt`.)
- **LOGAN_2 stop 3 (Jetbridge)** — a **1632** land grant to Governor John Winthrop
  and Fort Winthrop, three centuries too early for a boarding bridge. (Verified in
  `TOURS_FOR_REVIEW/round7/LOGAN_2.txt`.)

This is D571's venue-parts problem in reverse: the parts were chosen correctly, then
filled with material belonging to the venue as a whole. It is distinct from D584
(which caps one PERSON across stops) — this is a STORY landing on a part it cannot
belong to.

## The fix — a part has an earliest possible date

`venue_parts.py`, in `distribute_lore` (the function that hands each chain fact to a
stop). The insight, and the tour's own words prove it: the part has an earliest
possible year, and material older than it does not belong on it. The tour already
knows 1959 — it says so.

Added to `venue_parts.py`:

- **`PART_KIND_EARLIEST_YEAR`** — an offline table of the year a KIND of part could
  first exist: jet bridge / jetway / boarding bridge / passenger boarding bridge =
  **1958**, control tower = 1930, escalator = 1900, security checkpoint = 1973,
  baggage carousel = 1962, etc. Conservative: only hard technology floors, earliest
  defensible year, so the gate rejects only the indefensible.
- **`part_kind_earliest_year(name)`** — the floor for a part's kind, or `None`.
- **`part_earliest_year(name, part_built_years=None)`** — the LATER of the kind
  floor and this instance's build year (a source saying a concourse opened in 1975
  makes 1975 the floor even though "concourse" has no kind floor).
- **`fact_earliest_year(text)`** — the EARLIEST four-digit year a fact names (1927,
  not a later rebuild year), or `None` if undated.
- **`fact_predates_part(text, name, part_built_years=None)`** — `True` only on
  positive knowledge: a year in the fact AND a floor for the part AND the year is
  older. No year, or no floor, means the fact fits (D577 — never drop on absence).

`distribute_lore` now refuses a predating fact at all three assignment paths — the
`placed` binding reason, the token-match, and the redistribution of unclaimed
venue-level facts. A refused fact is offered to the other stops and rehomed to one
that CAN hold it; only a fact that no part can host is dropped, and every drop is
recorded under `lore['_anachronistic']` so the decision is inspectable, never silent.
The new parameter defaults to `None`, so the existing `build_tour_stops` call site is
unchanged and backward compatible.

## Why it is general, not a jetbridge special-case

- A **1632 land grant on a 1970s concourse** is refused by the instance-year floor
  exactly as it is on the jetbridge (test `test_1632_refused_on_a_1970s_concourse_instance`).
- The **control-tower kind floor (1930)** refuses a 1927 fact even there
  (`test_control_tower_kind_floor_refuses_1927`).
- A venue of **floorless parts** (a church's nave, altar, stained glass) is left
  entirely untouched — nothing is refused when nothing is known
  (`test_a_floorless_venue_is_untouched`).

## Why it is deterministic / offline (Gemini 402)

The kind-floor table needs no network. The task's brief notes Gemini is returning
HTTP 402; the round-8 regeneration proved the defect survives on the current tree.
The check therefore does not depend on any grounded call — it runs in the offline
`distribute_lore` path. The instance-year hook (`part_built_years`) is available for
when a grounded build-year is known, but the fix does not require one.

## Tests

**New — `test_local528_date_vs_part_anachronism.py`: 15/15 pass.** Built from the two
real LOGAN stops quoted from the round-7 files:
- helper knowledge (synonyms → 1958, floorless → None, instance-year override,
  earliest-year extraction, positive-knowledge-only `predates`);
- LOGAN_1 jetbridge: 1927 Lindbergh refused; 1959 (the date the tour already holds)
  and 1964 Beatles allowed; an anachronistic placement `why` refused and logged;
- LOGAN_2 jetbridge: 1632 grant refused; dropped + recorded when no part can host;
  rehomed when a floorless part exists;
- general: 1970s concourse refuses 1632; control-tower floor refuses 1927; floorless
  church untouched.

**Regression:**
- `tests/test_d571_venue_parts.py` — 9/9 OK
- `test_local402_temporal_coherence.py` — 11/11 OK
- `python3 -m py_compile venue_parts.py test_local528_date_vs_part_anachronism.py generate_tour_text.py` — OK

**End-to-end** offline `build_tour_stops` harness (airport, 4 parts): the jetbridge
no longer receives the 1927 Lindbergh story via either the placement reason or the
token match, and `_anachronistic` records `('Jetbridge', 1927)`; the 1959/1922/1964
facts flow to other stops.

## Evidence for the 1958 floor

`web_search` (Serper), 2026-09-23: the first operational "AeroGangplank" was
installed by United at Chicago O'Hare in **1958**; the first twelve Jetway passenger
boarding bridges were installed in **1959** (Wikipedia "Jet bridge"; JBT AeroTech
Jetway Systems; Simple Flying). 1958 is used as the earliest defensible floor.

## Grounded-run note

No grounded generation run was performed: Gemini is at HTTP 402 (prepayment credits
depleted), so a full LOGAN regeneration through the live chain is not possible right
now. Per the brief, I delivered the offline part — the fix, its unit/acceptance
tests, and an offline end-to-end `build_tour_stops` harness — rather than fabricate a
verification run. When Gemini credit is restored, regenerating LOGAN_1/LOGAN_2 should
show the jetbridge stop free of the 1927/1632 material and either a jetbridge-era
fact in its place or the stop carrying its post-1958 content.

## Files

- `venue_parts.py` — knowledge table + helpers + `distribute_lore` integration
- `test_local528_date_vs_part_anachronism.py` — new test (15/15)
- `SUBMISSION_LOCAL-528.md` — this file
