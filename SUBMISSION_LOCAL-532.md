# SUBMISSION — LOCAL-532: LOGAN_1 spends its best anecdote (Lindbergh's landing) more than once

**Agent:** Mac Mini Kiro · **Branch:** LOCAL-532-best-anecdote-told-twice · **Base:** storied (65de385)

## What the critic said, and what I verified

The round-7 critic (`CRITIQUE_ROUND7_517.md`): *"Lindbergh appears in two of four
stops - the file tells its single best anecdote twice."*

I verified against the real file and the critic **undercounted**. Lindbergh is in
stops **1, 3 AND 4** — three of four:

```
python3 -c "import re; t=open('TOURS_FOR_REVIEW/round7/LOGAN_1.txt').read(); \
  print([i+1 for i,p in enumerate(re.split(r'^Stop \d+:',t,flags=re.M)[1:]) if 'Lindbergh' in p])"
-> [1, 3, 4]
```

Reading the file, the repeated unit is a single **EVENT** — Lindbergh's landing at
Logan — told twice in the BODY:

- **Stop 3 (Jetbridge):** "It was here, on the tarmac just beyond the bridge, that
  Charles Lindbergh once touched down, marking a significant moment in aviation
  history." — *no year in the sentence.*
- **Stop 4 (Control Tower):** "In 1927, ... Charles Lindbergh landed the Spirit of
  St. Louis here during his goodwill tour, only months after his historic solo
  transatlantic flight." — *dated 1927.*

(Stop 1's Lindbergh mention is in the Orientation preview — "the historic landing of
Charles Lindbergh's Spirit of St. Louis at Control Tower" — which is deliberately
exempt from repeat rules per Michael's D534 instruction and is not the target here.)

## Why the existing guards let it through

- **`strip_cross_stop_repeats` / `_same_episode`** match on person **AND** year. The
  stop-3 telling carries no year in-sentence, so `years_a & years_b` is empty and the
  pair reads as two unrelated mentions. Word-overlap (Jaccard) misses it too:
  "touched down" vs "landed the Spirit of St. Louis" share almost no content words.
- **`cap_person_across_stops` (D584)** caps a person at 2 stops. Lindbergh is in
  exactly two BODY stops, which D584 permits by design.

So the same landing is narrated twice and nothing collapses it.

## The change

`derepetition_guard.py` — added an EVENT-level detector and wired it into
`strip_cross_stop_repeats`:

- `_EVENT_ACTIONS`: a small map of action-classes (arrival, visit, birth, death,
  founding, construction, performance, ceremony) to the verbs/phrases that name them.
- `_event_key(sentence)` -> `(people, action-classes, years)`. People reuse
  `_person_names` (so common-noun scaffolding like "windows"/"church" is excluded).
  A sentence with no action verb yields an empty action set and matches no event —
  so atmospheric prose ("continues the legacy that Lindbergh symbolized") is inert.
- `_same_event(a, b)`: matches when the two tellings share an actor **and** an
  action-class, and the year is **not in conflict**. The year is used as a
  **separator, not a required match**: equal years, or a year on only one side, or
  no year at all = same event; two *different* explicit years = two distinct events.
- In `strip_cross_stop_repeats`, each sentence's event key is compared against the
  earlier stops' keys (before Jaccard). A later telling of the same event is dropped;
  the earliest telling is kept. Same `removed_log` shape, so the existing pipeline
  log line is unchanged.

## Verified against the two real LOGAN_1 stops

With the stop bodies fed as the pipeline stores them (narration only; metadata and
the stop-1 orientation preview are not part of `description`):

```
Lindbergh present before strip: [3, 4]
strip_cross_stop_repeats removes: stop 4 <- matched stop 3
  "In 1927, ... Charles Lindbergh landed the Spirit of St. Louis here ..."
```

The first telling (stop 3) is kept; the later duplicate (stop 4) is removed; stop 4
retains its own distinct facts (43.5M passengers in 2024, the 1922 Governor Channing
H. Cox authorization, $35,000 for runway prep). This is asserted by
`test_real_logan_1_lindbergh_landing_told_twice_is_collapsed`.

## How this composes with D584 (required by acceptance)

They govern different units and cannot disagree:

- **D584 (`cap_person_across_stops`)** governs how many STOPS a *person* may appear
  in (≤ 2). It never fires for a person in two stops.
- **LOCAL-532 (`_same_event`)** governs whether the same *EPISODE* is NARRATED more
  than once. It is a strictly narrower unit: person **+ same action-class + a
  non-conflicting year**.
- Removing a duplicate telling only ever REDUCES a person's stop reach, so it can
  never push a tour past D584's cap. And the case D584 exists for — a person in two
  stops for two *different* dated events (Cuenin, 2002 ovation and 2005 removal) — is
  exactly the case `_same_event` declines (different explicit years). Verified in
  `test_different_years_are_two_events_not_one` and
  `test_strip_does_not_collapse_two_different_dated_events`.

Order in the pipeline (unchanged): D584 person-cap → orphaned-pronoun cut →
`strip_cross_stop_repeats` (now also event-aware).

## Tests

New: `tests/test_local532_event_repeat.py` (8 tests) — unit discrimination
(single-side date, no date, different years, different action-class, different
people, no-action-verb) + integration (keeps first telling, declines two dated
events) + verification against the real `TOURS_FOR_REVIEW/round7/LOGAN_1.txt`.

```
python3 -m pytest tests/test_local532_event_repeat.py tests/test_d584_person_cap.py \
  tests/test_d533_cross_stop_facts.py tests/test_d534_any_repetition.py \
  tests/test_local280_closing_recap.py tests/test_local44_stop_preaching.py \
  tests/test_local48_substance_rebase.py -q
-> 90 passed, 1 warning
```

(The single warning is an unrelated urllib3/LibreSSL notice, not from this change.)

## Grounded calls

None required. Detection is offline (regex + set logic over the tour text) and was
verified against the committed round-7 fixture. Gemini's HTTP 402 is therefore not a
blocker for this task — no live/grounded run was needed, and none was fabricated.
