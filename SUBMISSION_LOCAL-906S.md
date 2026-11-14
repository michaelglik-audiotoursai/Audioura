# SUBMISSION LOCAL-906S — language, fragments, destination stop (offline, $0)

Branch `LOCAL-906S-language-fragments-dest`, base a60107db (`git merge-base --is-ancestor a60107db HEAD` = 0).
No live run, no paid call (`env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`). No budget spent.

## What changed
New module `language_dest_906s.py` (pure, never raises, generic names). It runs as the very last delivery guard in
`delivery_bodies_905.ensure_bodies`, after the 906R `last_word`. Small hooks elsewhere:

- `owner_junk_906p.junk_reason`: also asks the 906S caption detector (so refills see it too).
- `refill_quality_906k.refill_reject`: a foreign-language sentence, a caption, an operator/closing line, a fragment or "connects" filler is never a refill.
- `route_content_896.is_fragment`: also asks `fragment_reason` (906B's `is_verbless` accepted any -ed/-s word as a verb).
- `leftovers_906f.refill_thin_stops`: logs why a thin stop got no refill (counts per rejection reason, or "no evidence for this title").

| # | Item | Behaviour |
|---|------|-----------|
| 1 | foreign sentence | English-function-word share >= 20% = English; otherwise stop-word hits (vi, es, fr, de, it, pt, id) or a Vietnamese-letter density -> dropped, even if it was the stop's last sentence. Runs only when the tour itself is English. No `langdetect` dependency. "Mũi Né is a coastal fishing ward in the Lâm Đồng Province" is kept. |
| 2 | caption variants | "A (person/man/woman/child/group/people...) <verb>s ..." <= 20 words, alone or after a "<Place>, <Place>," prefix. `has/is/was/does/lives...` are not verbs here. |
| 3 | title as a place | Dash titles and topic-like titles (906O `is_topic_like`): subject -> `name_cores` core ("The Arriving at <Name> – the mountain ..." -> "<Name>"), topic title -> "This area"; "Look for <Title> in <Ward>." -> "You are now in <Ward>.". Named, non-dash titles are untouched. |
| 4 | "known for <verb>" | clause cut when the head stands alone, else the sentence is dropped. Nouns/gerunds after "known for" are kept. |
| 5 | fragments | "As you explore, known for ...", "<Name>, located ... in <District>." (no finite verb after the participle), "one of the longest <X> statue on a mountains" -> plural noun and the broken "on a mountains" tail cut. "The temple is located ..." / "<Name>, located ..., is a popular site." are kept. Why they passed 906B: `is_verbless` counts any -ed word ("located") or any verb in a subordinate clause ("explore") as a verb. |
| 6 | Their/They | no plural referent in the stop (earlier sentences, earlier in the sentence, or the title) -> sentence dropped. "two centuries" is not a referent. |
| 7 | destination stop | "This stop connects ... earlier ... tour" is filler (always dropped). A stop whose sentences are all template filler (or has none) is refilled (906I refill with the filler still present so it counts as thin), then the filler goes; with no supported sentence it gets the D760 disclosure body (same `sensory_body` call as `ensure_bodies`). |
| 8 | cross-stop measure | same dimension + shared object noun + >= 2 shared object words across stops -> the article value from any stop (else the single value the evidence states). With neither, the later stop's measure clause is omitted (else its sentence). Logged. |
| 9 | operator / closing | "These tours ...", "tours often start/depart ...", "offer private charters", "recommended ways to get here", "explore nearby attractions", "personalized experience", "This tour showcases/highlights ...", "Each stop invites ...". Closing lines too; the count line and the restaurant offer stay. |
| 10 | period claims | a decade ("the early 2000s") / century phrase the stop's evidence carries no year/phrase for: the dated clause is cut, else the sentence is dropped; a "significantly increasing ..." tail with < 50% evidence token overlap is cut. A stop with no evidence at all is not judged. |

## Item 7: why the destination stop was not refilled (from the proof log)
The log has NO "906I thin after removals" and NO "906K refill candidate rejected" line for Stop 3, while `[LOCAL-906H] delivery
evidence: 3/3 stops`. So the refill ran (or returned early) with every candidate silently rejected before the logged 906K bar
(denied / unsupported / same-fact / owned-by-another-stop / pronoun / "you" / promo filters were silent), or the title lookup missed.
I cannot tell which from the log alone. Also: the 906R `last_word` only refilled when its own pass had changed the text, and the filler
sentences counted as body sentences. Fixes: every silent rejection is now logged with a count per reason, `last_word` of 906S always
checks for factless stops, and a stop with no supported sentence ends with the disclosure body instead of filler. Unproven live.

## Item 10: did 883/873C see "installed in the early 2000s"?
In the log the cable-car "early 2000s" sentences appear only as D534 "already told / removed" repetition lines and in 855B drops for
the dragon-fruit stop; there is no 883 labelled/kept verdict line for the delivered "installed in the early 2000s" sentence, so
no evidence check was applied to it. The new guard checks it against the stop's evidence.

## Tests
`tests/test_local906s_language_fragments_dest.py`: 45 tests. Usual set (task list, `test_local88_tour_pollution.py` deselected):
2786 passed, 4 skipped, 0 failed (the first run had one failure, `test_local894...::test_driving_register`, caused by my disclosure
register choice; fixed: walking only when the tour says "walking tour" and is not a drive).

Replay of the three 551/552 proof texts and `run2_551.txt` through `last_word` (offline, no evidence): the Vietnamese sentence, the caption,
the "As you explore" and "located about 40 minutes" fragments, "known for visit", "Their choice", the dash-title subject, the operator and
closing lines were dropped or rewritten; the destination stop (no evidence passed) got the disclosure body; the 552 "7 meters high"
conflict dropped the later stop's measure clause (with article evidence it takes the article value; unit test).

## Not proven / handing to LEAD
- No live run: the destination-stop refill cause (item 7) needs one run with the new "why no refill" log line.
- Item 5 agreement fix handles only a noun from a fixed list (statue, tower, temple, ...); anything else is left as is.
