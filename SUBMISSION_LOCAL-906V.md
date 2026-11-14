# SUBMISSION LOCAL-906V (offline, $0)

Branch `LOCAL-906V-drive-quality-repeats`, from 78379039. No live run, no paid call. Tests run with
`env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`. Fixtures use generic names (D769). The proof log was read, not copied or committed.

## Result
- New tests: `tests/test_local906v_drive_quality_repeats.py` (22 pass).
- The task's regression set (`test_local88_tour_pollution.py` deselected): 3012 passed, 4 skipped, 0 failed.
- Replaying the three 906U proof texts through `drive_quality_906v.last_word` (no evidence) removes the day-tour, neighbour, "unforgettable"
  and closing sentences, rewrites both wrong-leg Directions, drops the thread line from 552 Stop 1, tells the 551 Stop 6 legend once, and gives
  Drive Stop 1 the disclosure body. Run through `final_906u.run_pass`, 551 Stop 4's repeated 28 km is already one fact.

## Findings and fixes
1. **Factless Drive Stop 1.** The earlier sourced facts were removed by the 883 grounding gate (9 of 10 sentences UNSUPPORTED), then the 873C
   traceability check (2 sourced facts, narration rejected). What was left was one model-written sensory sentence. 906S `factless_stops`
   did not fire because `language_dest_906s._factual` only excluded template filler, the disclosure and `is_mood_filler`; the sentence has no
   mood term, so it counted as factual. **Fix:** `_factual` also excludes `drive_quality_906v.sensory_only` (no digit, no proper name,
   sound/scent/light cue with a sensory opener or two cues). Such a stop now goes through the 906I refill, else the D760 disclosure body.
2. **Backtrack stop.** `route_order_909.order_poi_list` calls `drive_quality_906v.replace_backtracks` after the 906P detour pass and after
   the water check. A stop whose detour (d(prev,X)+d(X,next)-d(prev,next)) exceeds 50 % of the direct leg and whose projection on A->B is
   < 0 is replaced from the pool (non-backtracking, detour under the 60 % limit), else dropped while at least two stops remain.
   Log: `[LOCAL-906V] backtrack stop rejected`. In the proof run the order pass never ran: `endpoints_pts` cached `(None, None)` after the 429s
   ("route endpoints: origin=None destination=None"). **Fix:** a failed endpoint lookup is no longer cached.
3. **Wrong leg in Directions** (`directions_pass`). In Stop N (N>=2) a sentence opening "From <earlier stop>," followed by a driving verb becomes
   "From here, ...". In a non-final stop, "to reach your destination" becomes "to reach <next stop>" when the sentence names the next stop, else the
   sentence is dropped. Stop 1's "From <Origin>, head to <Stop 1>." lead (909) is kept.
4. **Copy** (`copy_reason`, in bodies, Orientation and the closing paragraph): day-tour copy, "If you travel ... from here, you reach ...",
   "another popular destination", "... that many find unforgettable", and "(Exploring|Experiencing|Visiting|Discovering|Seeing|...) ...
   (allows|invites|lets|helps|gives|offers|...)" with no digit and at most one proper name. The closing paragraph needed its own pass
   (`closing_pass`): the last stop's "... That's N stops in all." line is not a body line for the sentence plumbing.
5. **Thread line in a stop body.** I could not reproduce the stage that put it in 552 Stop 1. `tour_conclusion.rebuild_conclusion` on a
   2-stop fixture puts the paragraph after the last stop. The one path I found that can carry a conclusion sentence into a stop body is
   `_salvage_after_count` (906B): a sentence after the offer skips the "names another stop" test. **Fixes:** `_salvage_after_count` never
   keeps a thread-template sentence, and `sentence_pass` drops it from the body of every stop that is not the last (the last stop's
   closing is already covered by 906 `drop_template_closing`). Not proven live.
6. **Same distance twice.** `final_906u.sentence_pass`: equal values (within 0.5) from the same reference are one fact; the
   "<X> is N km <dir> of <City>, in ..." location lead goes, else the later sentence. Source: the 906I refill
   (`leftovers_906f.refill_thin_stops`) took an encyclopedia lead whose distance `same_fact` did not match (different wording). **Fix:** the
   refill refuses a candidate whose distance a stop sentence already states (`distance_duplicate`).
7. **Legend told three times** (`retold_pass`). Sentences of one stop are clustered when they share >= 60 % of content words (min 5),
   share two event classes (legend / recognition / healing), share one class plus a proper name that is not in the title, or match
   `derepetition_guard._same_event`. The most specific sentence of each cluster (`specificity`, earlier on a tie) stays. On the proof text
   the three retellings go and the "conferred royal recognition" sentence stays.
8. No new "From the vehicle" cases; 906U's guard is unchanged.

## Wiring
`delivery_bodies_905.ensure_bodies` calls `drive_quality_906v.last_word` after 906U. It runs the pass, refills or discloses a stop left
without a factual sentence (906S `factless_stops`), and runs the pass again.

## Not proven live
Offline only. The disclosure that replaces Drive Stop 1 depends on the live evidence: with sourced sentences the refill path runs first.
The backtrack guard needs the origin and destination to geocode at pre-writing time. The thread-line source is a candidate, not a reproduction.
The earlier-stop rewrite in Directions relies on the Directions naming the earlier stop with its title.

## Files
New: `drive_quality_906v.py`, `tests/test_local906v_drive_quality_repeats.py`.
Edited: `language_dest_906s.py`, `route_order_909.py`, `delivery_bodies_905.py`, `leftovers_906f.py`, `final_906u.py`, `tour_conclusion.py`.
