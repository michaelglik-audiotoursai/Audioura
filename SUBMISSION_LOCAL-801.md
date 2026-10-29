# SUBMISSION — LOCAL-801: duplicate stops, "6 stops for 5", mid-clause text collisions

**Branch:** `LOCAL-801-dupes-collisions` (base `subscribed` 4bae2595)
**Arm fixed:** the DEFAULT arm (gpt-4.1 narration — the cloud setting), found by the
Oct-28 P1 blind scoring. (LOCAL-654 fixed the same *shapes* on the cheap arm on Oct 9.)

## The defects (from p1/P1_RESULTS.md + p1/out/A_*.json)

On Arm A (gpt-4.1):

- **w1 Freedom Trail (5 requested)** — Park Street Church delivered twice; the tour
  reported **6 stops for a 5-stop request**; score 4.0.
- **w3 Salem (4 requested)** — The Witch House duplicated; "5 stops in all".
- **w4 Old Saigon (5 requested)** — Independence Palace's body spliced into Stop 1.
- **d1 JP coffee (3 requested)** — severe **mid-clause collision** in Stop 1; score 4.5.
- **d2 North End (3 requested)** — the pair the ticket named; in the saved A text it is
  structurally clean (used here as the "must stay unchanged" control).

## Root cause (diagnosed offline from the saved A texts)

Two mechanical corruptions on the default arm, both reproduced byte-for-byte in
`tests/fixtures/local801/`:

1. **Duplicate stop + overcount.** A stop's `Directions:` line was followed by a
   *headerless* copy of the **next** stop's body (Address/Coordinates/Type/Orientation,
   no `Stop N:` of its own), then a **stray preview header** rendered as a real header —
   `Stop 3: Boston Common — it is roughly 1.1 km … away.` — then the real stop. So the
   same stop appeared twice and `count_delivered_stops` (which counts `Stop N:` headers)
   over-counted, making the closing line say "6 stops in all".

2. **Mid-clause collision.** A sentence pass that split on a naive `period + space`
   boundary cut the brand `J.P. Licks` at the abbreviation dot, dropped/re-ordered the
   fragments, and re-welded mid-clause:
   `"This route takes you from J.P. These stops reflect … Jamaica Plain. Licks in June
   2021 … at J.P. Your first stop is J.P. Licks.P. Licks.P. Licks."`
   The shared abbreviation-aware splitter (`sentence_split.split_sentences`, LOCAL-654)
   *does* keep `J.P.` attached — so the corrupting pass on this arm did not use it.

## The fix — `stop_dedup_collision_guard.py` (new, pure/deterministic/offline/idempotent)

- `dedupe_and_fix_stop_count(text, requested_stops=None, dedupe_real_stops=True)`
  - drops **stray preview headers** (`Stop N: … — it is roughly … away.`);
  - **de-splices** a headerless body glued after a `Directions:` line (keeps the hand-off
    sentence, drops the spliced copy);
  - optionally dedupes **true duplicate** real stops by normalised title, or a *contained*
    title corroborated by coordinates within **60 m** — **never coordinates alone**
    (Old Saigon's five distinct District-1 places sit within ~50 m of each other, and
    Salem's Witch Museum is ~57 m from the Trials Memorial — coordinate-only dedup would
    wrongly merge them);
  - renumbers survivors `1..k`; can cap to `requested_stops` so delivered ≤ requested.
- `repair_collisions(text)` — the **garble guard**:
  - collapses a welded repeat (`Licks.P. Licks.P. Licks` → `Licks`);
  - splits a sentence at a **collision glue** (a dotted abbreviation welded directly to a
    sentence-starter: `J.P. These`, `J.P. Your`) and drops the dangling fragment / orphan
    opener left behind;
  - keeps grammatical prose intact — the legitimate lawsuit sentence
    `"… filed a lawsuit against J.P. Licks, demanding …"` has no glue and is preserved;
  - logs `[LOCAL-801] collision repaired <stop>` on every repair.

### Wiring — one choke point

Both guards run inside `tour_conclusion.normalise_stop_headers`, which
`count_delivered_stops`, the conclusion rebuild and every finalization path already call.
So the delivered count, the "That's N stops" sentence (rebuilt from that count) and the
text all agree, and a "6 stops for 5" over-count cannot survive.

The choke-point call uses `dedupe_real_stops=False`: it strips only the **artifacts**
(preview headers + spliced bodies) and must not drop a *legitimately repeated* real title
(a museum's two views of the same wall — LOCAL-639). Same-title dedup of real delivered
stops stays where it already lives, in the delivery path (`stop_title_dedup` / LOCAL-722).
On clean text both guards return the input **byte-for-byte** (verified against the
service's `_header_formatting_defect` and LOCAL-639's `normalise(text) == text` contract).

## Tests

`test_local801_dupes_collisions.py` — **18 tests, all pass** — on the exact P1 strings:
- each fixture reproduces its defect (guards against a stale fixture);
- dedup gives w1=5 / w3=4 / w4=5, with the coordinate-clustered distinct places all kept;
- collision repair fixes d1, preserves the lawsuit sentence, leaves clean prose and
  `St. Mary's` / `U.S.` untouched, collapses the weld;
- the wired `count_delivered_stops` corrects the overcount directly on the raw fixtures;
- idempotency; clean-tour-unchanged (d2); empty / headerless inputs.

### Regression

- Header/dedup/conclusion/walking/sentence family (642, 639, 639-NG, 743, 619, 654, 626,
  614, 660, 662, 658, 650, 646, 722, 617, 630, lead-double, 616, …): **345 pass / 3 skip**.
- Full root suite: **1975 pass, 30 fail** — all 30 confirmed **pre-existing** (verified
  representative failures reproduce with this change removed; they are ranking / lookups /
  facility / site-first / hygiene / day-range / network tests, none touching stop-count or
  collisions).
- `tests/` conclusion/stop-relevant failures (373, 494, 778, 85) verified **identical with
  the guard enabled vs the module hidden** → pre-existing.

## Live proof — DEFAULT arm, isolated `-p local801`, cap $1.50

`run_local801_live.sh` (own throwaway postgres, **no** `NARRATION_MODEL`/`TOUR_LLM_MODEL`
override, `RESEARCH_BACKEND=serper` because Gemini prepaid credit is depleted) →
`run_local801_container.py`:

- **w1 Freedom Trail (5):** delivered **5/5 distinct** stops [Boston Common, Massachusetts
  State House, Park Street Church, Granary Burying Ground, King's Chapel], "That's 5
  stops", **no** Park Street Church duplicate, **no** stray preview header, **no**
  collision. (P1 was 4.0.)
- **d1 JP coffee (3):** delivered **3/3 distinct** [Ula Cafe, Tres Gatos, J.P. Licks],
  "That's 3 stops", **no** weld/dangling collision, **no** duplicate/preview. (P1 was 4.5.)
- Spend **$0.2059** of the $1.50 cap, **2** tours (≤ 4). Grounding **$0** (6 requests, 0
  Gemini queries) — Gemini was not needed, so no step is UNPROVEN.

(The throwaway postgres was an empty image with no `audio_tours` schema, so the `is_test`
insert was a no-op; acceptance was evaluated on the generated text directly, which is
authoritative. No live DB was touched; no `DELETE`.)

## Files

- `stop_dedup_collision_guard.py` — new guard (dedup + garble).
- `tour_conclusion.py` — wire both guards into `normalise_stop_headers` (+24 lines).
- `test_local801_dupes_collisions.py` — unit tests.
- `tests/fixtures/local801/{w1_freedom_trail,w3_salem,w4_old_saigon,d1_jp_coffee,d2_north_end}.txt`
  — verbatim P1 A texts.
- `run_local801_container.py`, `run_local801_live.sh` — isolated live harness.
