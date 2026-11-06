# SUBMISSION LOCAL-870: wave-28 findings

Branch `LOCAL-870-wave28-fixes`, from `b5405323` (subscribed). Merge-base check: `git merge-base --is-ancestor b5405323 HEAD` exits 0.
Live proofs (Mac-local, own postgres :55970, TASK_BUDGET_ID=LOCAL-870): **$0.4312 of $0.70** (Sophia $0.2176, 10-stop import $0.2136). TTS was captured, not called. No live-DB write, no shared container touched, `review_queue` untouched.

## What changed

| # | Finding | Fix | Files |
|---|---|---|---|
| 1 | LGBT bar rated Mature | Rater prompt: sexual orientation / gender identity (LGBT or gay bar, drag, Pride venue) is never a reason for mature or not_allowed. Drag, karaoke, live music, comedy, dance and spa are ordinary entertainment. Drinking and nightlife make a tour mature only when they are its primary purpose. | `tour_content_rating.py` |
| 2 | 🌈 in `audio_N.txt` / TTS | New `_strip_emoji_from_stop_texts` runs after geocoding and before TTS, and again when the ZIP's `audio_N.txt` is written. Log: `[LOCAL-863] TTS emoji strip at <where> audio_<n>.txt: removed N`. It prints with `flush=True`. | `tour_generation_modernized.py` |
| 3 | Last of a cluster keeps a model pin | In the pin-snap clear pass, a USER stop whose coordinate is model-sourced and that has no reference is cleared whatever its neighbours are. Log: `[LOCAL-870] user stop … only a model coordinate and no reference`. The orchestrating call passes `is_user_stop_fn` so the job's user-title set counts too. | `pin_snap.py`, `generate_tour_text.py` |
| 4 | Famous landmark user stop is thin | `classify_stop_kind` returned business for any business-looking Type before looking at the name. It now returns landmark when the name has no business word and either the offline Wikidata landmark table knows it or the name has an institutional word (opera, cathedral, palace, museum, temple…) with only weak business words in the Type (venue, music, live…). | `user_stop_enrichment.py` |
| 5 | Person name / address given a word etymology | `person_name_span` finds a Vietnamese person name. `bridge_sentence` then gives "It is named after X." (name is only the person), "The cafe takes its name from its address on X." (house number + street), or no bridge. The name-meaning lookup skips surname and given-name tokens, so no surname etymology is fetched. | `user_stop_context.py` |

## Item 1: policy check (cited)

`legal/CONTENT_POLICY.md` ("Mature (18+)"): "a tour whose **primary purpose** is drinking, such as a bar crawl, wine or spirits tasting, or cocktail bars; … gambling and casinos, or **nightlife as entertainment**". General covers "food and drink in ordinary context". Nothing in the policy mentions sexual orientation or gender identity, so neither can be a Mature signal.

Two things to know:
- **The rater's stored reason for 534 was not read.** That needs the live DB, which was off limits. I inferred the cause from the prompt: its "nightlife/clubs" and "bar" wording, plus a tour called "bars" containing a gay bar and karaoke. The prompt now has the orientation rule above. It also makes the primary-purpose test explicit, as the policy does.
- **A real bar crawl or cocktail-bar tour is still Mature, by policy.** I did not loosen that. If Michael wants a tour made only of bars to be General, that is a policy change, not a prompt fix. `review_queue` approval rights are unchanged (Michael).

Tour 534's DB row stays `mature/pending` until it is re-rated after deploy. I did not write the DB.

## Tests

`tests/test_local870_wave28_fixes.py`: 18 pass, 2 skipped (live rater test, opt-in via `RUN_LIVE_RATING=1`).
- Run against base source (fixes stashed) it gives **11 failed, 6 passed**, so the tests are red without the fixes.
- The prompt tests are offline and only assert the instruction text and that `classify` sends it. The LGBT-bar → General and explicit-sexual-content → Mature checks need a real model: the live test file covers them, and the live run below used the real rater on the Sophia text. The explicit-content fixture was not run live, to save budget.
- Regression suites run green: 687, 724, 724b, 726, 791c, 815, 847, 860, 862*, 863, 801, 858b, 855*, 866, 867, 859 (481 tests in the two batches, all pass).

## Live results

Sophia, 7 stops (`_local870_meterlogs/sophia_run.txt`, kept out of git):
- 7/7 delivered.
- **Rater: general.** Reason from the model: "factually describes cultural, historical, and entertainment venues including nightlife and bars without focusing on drinking as the primary purpose or glamorizing crime or adult content." This was run on the Mac-regenerated text, not on tour 534 itself.
- **No emoji** in any of the 7 `audio_N.txt` and none in the 7 captured TTS payloads. The generator text did contain 🌈. Log lines: `[LOCAL-863] TTS emoji strip at tour-modernized audio_4.txt: removed 1 emoji run(s)` and `… audio_5.txt: removed 3 emoji run(s)`.
- **A Star is Born** has no Coordinates line (announced with no pin). Log: `[LOCAL-870] user stop 'A Star is Born' has only a model coordinate and no reference — announced with no pin`.
- Side effect: Longan and Rambutan also get `[LOCAL-870]` lines. They are user stops with model coordinates and no reference, so they were already unpinned by the 858B cluster collapse in wave 28 and now are by the new rule.

10-stop import (`import10_run.txt`):
- 10/10 delivered.
- Saigon Opera House: log `[LOCAL-862] Saigon Opera House: landmark kind — existing story path kept`. The body is 6 sentences, 176 words, about Ferret and the 500-seat design and the Beaux-Arts façade. No "known for performances / before you go in" form.
- Name bridges: no "word Nguyen" bridge and no surname etymology for Book Street or Café Apartments 42. Café Apartments gets no bridge; the stop text contains no name-meaning fact for it.

## Not verified / limits

- The wave-28 cloud log had no `TTS emoji strip` line even though the old code already stripped at the payload. I could not see why (a Cloud Run log or stdout-buffering cause is plausible, but unconfirmed). I made the strip log with `flush=True` and added the `audio_N.txt` strip, which the old code never did. Whether the line appears on Cloud Run needs a deploy to check.
- Item 4: I could not see Opera House's Type label in the wave-28 run, so I treated the cause as "business-looking Type beats a famous name". The fix covers Types like "Live music venue" or "Concert hall". Wikipedia/canon content for it comes from the existing landmark path, which the run exercised.
- Pre-existing, not touched: Book Street's body says its name is "associated with Đường sách … named after the leader Hồ Chí Minh". That is an unsourced name claim, not a person-name etymology, and I did not change it.
- The stray `prompt_dump_*` and generated tour files from the live runs were removed or restored and are not committed.
