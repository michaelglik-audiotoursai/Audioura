# SUBMISSION — LOCAL-862: the listener's own stops, interesting AND true

**Branch:** `LOCAL-862-user-stop-stories` (base `subscribed` 7ab51728; `git merge-base --is-ancestor 7ab51728 HEAD` = 0)
**Verdict: NOT a full PASS.** Two of three criteria met; criterion 1 reached **4 of 7**, not 5. The three
missing stops have no discoverable source under the names and pins we were given (evidence in §4).
I did not pad them.

## 1. What changed

| File | Change |
|---|---|
| `user_stop_enrichment.py` (new) | Routes BUSINESS-kind user stops through the business-tour enrichment: **Serper Places record** (rating, count, price, website, address, category, hours) → **customer_voice** (one review search, LOCAL-800) → the **venue's own website** (homepage + one /about page, robots.txt respected, ≤ 2 pages, social/aggregator hosts skipped, private IPs refused) → **one story search** `"<name>" <city> history OR owner OR founded OR story`. Output is a numbered FACT LIST, each fact with its source. ONE batched gpt-4.1-mini call narrates every rich stop (one orientation sentence plus a 3–6 sentence body) with that list as its ONLY source. Fewer than 2 sourced specifics → a short deterministic stop built from Places data only. Landmark-kind stops are left alone. |
| `user_stop_verify.py` | The 855D verifier now judges a narrated stop against the SAME material (`material_by_title`; no second Serper query) and skips precomposed thin stops. Prompt clarified: a date, person or event *stated by a source* is SUPPORTED. Landmark skip now uses name + type (`classify_stop_kind`). An Orientation line emptied by drops is refilled from the surviving body. Logs every dropped sentence. |
| `user_stop_narration.py` | 855B final scrub uses the same landmark test. The admin-geography number pattern no longer reads "28,000 reviews" as a population. |
| `places_search.py` | Carries `openingHours` as `_serper_hours`. |
| `generate_tour_text.py` | Calls the enrichment just before the 855D verifier and passes its material through. Keeps the Maps-URL place name per job (`_J._USER_STOP_ALIASES`, e.g. "The Crazy street" → "Bui Vien Walking Street"). `USER_STOP_ENRICH=0` disables it. |
| `run_local862_live.py`, `run_local862_replay.py` | Live harness (855E inputs, cumulative budget-enforced meter) and an enrichment-only replay used for cheap iteration. |
| `tests/test_local862_user_stop_enrichment.py` | 25 offline tests (all network injected). |

### Truth rules that came out of the live runs (each one has a regression test)
* **Places record must be THIS venue.** The name or Maps alias must match ≥ 0.6, within 250 m of the pin. The only exception is up to 1 km when the record's website is the venue's own domain spelling its name (`an-spa.vn` for "An Spa"). A record admitted that way gives **brand facts only** (kind, own site), never that branch's address, hours or rating.
  Without `gl`/`ll`, Serper returned a resort in Townsville for "Rambutan".
* **Snippets must be about the venue.** The name (or alias) must appear as a phrase, with a venue noun within 6 tokens, a locality term (city/alias/district/own street), and no house-number address on a different street.
  The rejected cases are real snippets from run 1: the rambutan fruit, the Long An province wiki page, the *A Star is Born* film, "crazy street traffic of Hanoi", a Hoi An spa, and the Acoustic Bar branch on Nam Kỳ Khởi Nghĩa.
* **The generator's Type/Specialty and Specific Examples lines are guesses.** Run 2 shipped "A Star is Born is a café … artisan coffee, homemade pastries" and "Longan is a dessert shop". These lines now state only the Places category or a kind word in the venue's own name; otherwise they are removed.
* **Landmark detection doesn't depend on a random Type label.** Independence Palace was gutted when its Type came back "Historical Site" instead of "Historical Landmark".

## 2. Live — budget enforced
`TASK_BUDGET_ID=LOCAL-862 TASK_BUDGET_USD=0.60`, meter contract, OWN meter dir `./_local862_meterlogs` (D753 Mac-local escape hatch, `METER_MOUNT_GUARD=0`). No shared containers, no live DB, no phones.
Inputs: the 7 Sophia venues with the Google Maps place URLs from `run_local855e_live.py`, plus the Notre-Dame 3-stop regression.
**Cumulative metered spend for the whole task: $0.502 / $0.60** (6 live runs, 1 replay, Places/organic probes). Final run: $0.063.

Artifacts in `submission_artifacts/local862/`:
* `live_tour_7stops_run1.txt` (delivered)
* `enrichment_report_run1.json` (every fact and its source, per-stop calls and cost, narration before verification)
* `live_tour_notredame_3stops.txt`
* `baseline_855e_run1.txt` (copied from `LOCAL-855-user-stop-narration`)
* `meter_ledger.json`

Harness checks (final run): 7/7 delivered, all pins 0 m from the input, no "Đ." stub, no sea/coast/harp/altar/poster words, each stop on-venue, Notre-Dame keeps 1877/1880, Independence Palace keeps its sourced history.

## 3. PASS criteria

### (1) ≥ 5 of 7 stops with ≥ 2 sourced specifics — **4 of 7: NOT MET**
Only specifics that appear in the **delivered text** are listed.

| Stop | Sourced specifics in the delivered text | Source |
|---|---|---|
| The Crazy street | also known as Bùi Viện Walking Street | listener's Maps URL + Serper Places cid 17419937820716483494 |
| | 4.4 / 5 from ~28,000 Google reviews | Serper Places cid 17419937820716483494 |
| | about 850 m long | vinpearl.com/en/bui-vien-street-saigon-nightlife-hot-spot |
| | nightlife destination with neon-lit bars and live music | saigonadventure.com/bui-vien-walking-street-guide |
| | called "the craziest street in Vietnam" | facebook.com/visitistanbulofficial (travel-vlog post) |
| Thi Bar Saigon | gay bar | Serper Places cid 14207409389953159742 |
| | 224 Đề Thám | same |
| | 4.4 / 5 from ~1,200 Google reviews | same |
| An Spa | massage spa | Serper Places cid 15403763612159419680 (brand: own domain an-spa.vn, branch 796 m from pin) |
| | "Vietnamese Traditional Spa & Skincare" | an-spa.vn (homepage) |
| | signature facial lymphatic drainage massage with makeup removal and cleansing | an-spa.vn |
| | head/neck/shoulder massage, herbal compresses, acupressure | an-spa.vn |
| Acoustic Bar | live music bar | Serper Places cid 8955316489872957300 |
| | Ngô Thời Nhiệm / 6E Võ Thị Sáu | same |
| | 4.5 / 5, ~3,200 Google reviews | same |
| | open since 2007 | customer_voice review search (`since <year>` extraction); an earlier run also had scootersaigontour.com "Founded in 2007" |
| Rambutan | — (short honest stop) | nothing found |
| A Star is Born | — (short honest stop) | nothing found |
| Longan | — (short honest stop) | nothing found |

For comparison, 855E run 1 had **0** stops with a sourced specific. Its Type/Examples lines, e.g. "Restaurant and bar with a tropical theme", were generator guesses.

### (2) No invented history, legends or geography — **MET**
* 855B phrase lists on the delivered text: no legend, military, admin-geography, national-figure, firsts or no-direct-tie hit. The one remaining hit is the thin-only "dated claim" tier on Acoustic Bar's "Open since 2007". An offline re-scrub cannot see sources, but this date is sourced (table above).
* 855E invention words (sea/coast/harp/altar/film poster): none.
* 855D verifier dropped **5** sentences, against **45–52** per run in 855E. Each drop is logged. They were loose paraphrases of real facts ("the joy of music development" for the founder quote, an embellished FREAK SHOW line), the safe direction.

### (3) Rubric score above the 855E baseline — **MET, modestly**
`tour_rubric_scorer.py --n 7`: **855E baseline 39.29 → LOCAL-862 50.00**.
The structural surcharge is gone (−10.71 → 0). Every stop is still banded THIN, because the scorer counts dates, people and materials in the body and not ratings or treatments.
Per LEAD's warning the score proves nothing on its own. §3(1) is the real evidence.

## 4. Why only 4 of 7 (the blocker, with evidence)
The 855E inputs for Rambutan, Longan and A Star is Born are constructed `/maps/place/<Name>/@lat,lng` URLs, not real Google place records. Probes (all metered under LOCAL-862):
* Serper Places, `gl=vn`, `ll` at each pin (z17 and z18), queries by name, by name + city, and by name + kind: no record of those names within 2 km. Bare-name queries return a Sri Lankan "Rambutan" 10,200 km away, "Longan" paving firms in the US, and nothing for "A Star is Born". A karaoke search at the A Star is Born pin returns no karaoke venue near the pin.
* Organic search `"Rambutan" bar Saigon District 1`, `"Longan" bar Saigon`, `"A Star is Born" karaoke Saigon`: fruit beer, a Glenview IL restaurant, film soundtracks.

**What would unblock it:** Sophia's real share links from the field request (orch ef0cee57 / tour 523). Those are cloud-only, and the docstring copies are truncated. With a real place record, the enrichment path applies as it did for the other four. The right outcome for an unfindable venue is the short honest stop, which ships.

## 5. Cost
* Per business user stop: Places $0.002 + review search $0.001 + story search $0.001 + narration share ≈ $0.0003 = **$0.0043**. A thin stop costs $0.0040 (no LLM). An alias miss adds one Places call (+$0.002). Website fetches are free.
* Per tour (7 stops): enrichment **$0.0293** (Serper $0.028, LLM $0.0013) + verifier $0.0011.
* Extra versus 855E (one D759 query per stop, $0.007/tour): about **+$0.022/tour ≈ $0.003 per user stop**, under the $0.01 target. The verifier no longer makes its own D759 query for enriched stops.

## 6. Tests
* `tests/test_local862_user_stop_enrichment.py`: 25 pass.
* With `tests/test_local855*.py` and `tests/test_local860*.py`: 181 pass.
* Neighbouring suites (LOCAL-672/779/783/786/788/791/805/852/859, plus 800): 476 pass, 2 fail. Both failures are in `test_local672_verified_reviews.py` and **also fail on the untouched base** (`map_delivery/app.py` ModuleNotFoundError).

## 7. Known residuals
* The narrator sometimes still lists 4 items despite the ≤ 3 rule (An Spa).
* Results vary run to run: the story search returns different snippets each run, so a stop's specifics move between runs. The floor (Places record) is stable.
* `Specific Examples` is removed for enriched stops unless reviewers name items. The non-user-stop paths are unchanged.

---

# 862B — D760 layers: connected context + disclosed legend/speculation, never empty

Base `subscribed` 7ab51728, branch `LOCAL-862-user-stop-stories`. `origin/subscribed` merged: already contained, no-op.

## 862B.1 What changed
* **`user_stop_context.py` (new).** Layer 2, true connected context, from Wikipedia and Serper, each fact tied to something the venue has:
  * the **name's meaning** when the name is a word: Wikipedia Etymology plus the "hence the name" or "illusion of an eye" sentence (Longan: Chinese lóngyǎn, "dragon eye", Vietnamese *nhãn*; Rambutan: Malay *rambut*, "hair");
  * a name that is a **work's title** (A Star Is Born: the 1937 film and its remakes);
  * the **street's** documented story (Wikipedia: Bùi Viện Street, the Backpacker Quarter) and the **district's**, when the address names one;
  * the **tradition** behind what the venue offers (Vietnamese massage, karaoke, live music), whole sentences out of search snippets, never titles.
  There is deliberately **no city-level fallback**: a first run padded stops with the city's GDP and airport, which is exactly the unrelated regional history D759 forbids.
* **Layer 3, disclosed.** A legend from the word's Wikipedia "In culture" section or a snippet that actually tells a story, or an unverified claim ("We couldn't confirm this, but…"): a specific claim (year, "first", legend) resting on one third-party snippet that names the venue, or "the venue may have taken its name from that title".
* **One definition of "disclosed"**: `has_disclosure()`. The narrator is told the marker is required; `ensure_disclosure()` then adds `A folk tale tells that…` or `We couldn't confirm this, but…` to any layer-3 sentence it left bare, before verification.
* **Narrator** (`user_stop_enrichment.py`): facts are handed over in three labelled layers; 4–7 sentences, layer 1 → 2 → 3; every layer-2 sentence must contain the venue's name or "the name / the street it sits on / the tradition it belongs to"; never "the venue is a fruit". With no sourced kind the orientation is the deterministic "X is one of the stops you chose". A stop is narrated whenever ANY layer has a specific; the short deterministic stop is now only for all-three-empty.
* **Verifier** (`user_stop_verify.py`): the prompt knows the layers, and a deterministic `layer_gate()` runs after the model's labels:
  * a layer-3 sentence **without** a marker is dropped; a marker **without** a layer-3 source line is dropped (a marker never licenses an invention);
  * a year, "first" or geography that no source line contains is dropped **whether or not it is marked**.
* **855B scrub** (`user_stop_narration.py`): the always-drop legend and anecdote tiers now exempt a sentence that carries a disclosure marker, or that explains the word in the name. Dates, firsts and geography still drop.

## 862B.2 Tests (offline, `tests/test_local862b_layers.py`, 34 tests)
Required four:
* disclosed legend **kept**, the same legend undisclosed **dropped** (scrub tier and gate);
* name-meaning context **kept**;
* an invented date for the venue **dropped**, also when the sentence carries a marker.

Plus: a marker without a layer-3 source is dropped; the marker repair; the Longan, Rambutan, street, district and film-title contexts; a context-only stop is narrated, not thin; truncated-snippet trimming.
`tests/test_local862b_layers.py` + 862 + 855* + 860*: **214 pass**.

## 862B.3 Live — Sophia 7-stop tour, `TASK_BUDGET_ID=LOCAL-862B TASK_BUDGET_USD=0.50`
Own meter dir (`_local862b_meterlogs`), own process; no live DB, no shared containers (the cost-meter DB write fails to resolve `postgres-2` locally, as designed).

**How it was run, and the limit on it.** One full generation run (`run_local862b_live.py`) cost $0.265 on the ledger. That left $0.235, not enough for a second full run, so the fixes after it were verified by **replaying the enrichment + verification stage** (`run_local862b_replay.py`, ~$0.04 each) on that same generated tour. Generation is unchanged by this work, and enrichment/verification is the only stage that writes user-stop text, so the replay is the same code path, but it is **not** a second end-to-end generation. Spend: ledger $0.265 + replays and probes $0.19 (paid-API log $0.249 total) = **≈ $0.455 of $0.50**.

The first full run (before the fixes below) failed the 4-sentence gate (4 stops at 1–3 sentences) and showed three defects, all fixed:
* the gate called plain venue sentences "undisclosed legend" (token overlap with a layer-3 line; now counts only words unique to layer 3);
* the city-fallback padding (removed);
* a vague "legend of 'Rambutan' involving a kind figure" from a truncated Facebook title (now snippet text only, cut to a whole clause, and it must tell something).

### Final result (`submission_artifacts/local862b/final_tour_7stops.txt`)
| Stop | Sentences | Layers used |
|---|---|---|
| The Crazy street | 5 | venue (Places, snippets), street (Wikipedia Bùi Viện) |
| Thi Bar Saigon | 6 | venue, street/quarter, scene |
| Rambutan | 6 | name meaning (Malay *rambut*), "hence the name… hairy", **layer 3 folk tale** |
| A Star is Born | 4 | name is a film title (1937, remakes), **layer 3 speculation** |
| Longan | 6 | name meaning (*lóngyǎn*, *nhãn*, eye illusion), **layer 3 legend** |
| An Spa | 7 | venue (own site), Vietnamese massage tradition |
| Acoustic Bar | 7 | venue (Places, reviews), live-music scene |

**PASS 1 — no stop under 4 sentences: MET** (min 4, the offline report counts conservatively: it merges two sentences where the splitter does not break after a closing quote).

**PASS 2 — every legend/speculation sentence carries a disclosure: MET.** Every layer-3 sentence, with its marker:
| Stop | Marker | Sentence |
|---|---|---|
| Rambutan | `A folk tale tells` | A folk tale tells that in the Philippines, a man saved a deer from a tiger; the deer turned into a fairy named Rodona who granted him a wish and revealed the tiger was a witch named Matesa. (Wikipedia, Rambutan › In culture) |
| Rambutan | `A folk tale tells` | A folk tale tells that he chose a child, a girl named Rabona. (same source; the narrator split the tale in two) |
| A Star is Born | `We couldn't confirm` | We couldn't confirm this, but the venue may have taken its name from that title. |
| Longan | `A legend tells` | A legend tells of a young highly-skilled man named Longan. (snippet: hanting.delivery "the legend behind longan fruit") |

**PASS 3 — zero undisclosed invented venue facts: MET on the offline check, with caveats.**
* Every year or "first" in the delivered prose appears in a gathered fact for that stop (0 hits, `truth_report`).
* No undisclosed legend vocabulary.
* The 855B always-drop phrase lists on the delivered text: no hit.
* The verifier dropped 1 sentence (a city nightlife-ranking line on The Crazy street).
* I read all 7 stops against their fact lists. What I did **not** do is independently re-check each Wikipedia/Serper sentence against its web page.

**Weak spots, honestly:**
* **Longan's layer-3 line is thin and odd** ("a young highly-skilled man named Longan"). The better Longan tale (a hero who slew a dragon) came back in earlier runs, but the search results vary run to run. The tale shipped is disclosed and sourced; it is not a good story.
* **Rambutan's tale is Philippine.** Disclosed as such, but the listener may find it far from a Saigon bar. The narrator rule says to say "Vietnamese" only if the source does.
* **A Star is Born** has no layer 1 at all (Places finds no record at the pin, as in 862). Its four sentences are the film-title context plus one speculation, which is honest but not about the bar.
* **Thi Bar**: one sentence is garbled ("Along with Phạm Ngũ Lão and Đề Thám Streets, the street it sits on became known as…", the Wikipedia sentence names Đề Thám itself). True in substance, clumsy.
* Layer 3 appears at only 3 of 7 stops. Four have none because no legend or unconfirmed-claim snippet qualified; they are not padded.

### Rubric (reference only, the truth checks are the gate)
`tour_rubric_scorer.py --n 7`: 855E **39.29** → 852 **81.7** (as quoted) → 862 **50.00** → 862B **57.14** (base 60.71, structural −3.57).

## 862B.4 Cost
Per tour added over 862: context gathering costs 1–2 Serper queries per stop (about $0.008 for 7 stops: tradition, legend) plus free Wikipedia calls; narration is one batched call. Enrichment in the replay: $0.038–0.041, verify $0.002 per tour.

## 862B.5 Not done / follow-ups
* No second full end-to-end generation (budget, above).
* Ward/district from the pin alone (Nominatim returns post-reform wards such as "Bến Thành", no district). The district story applies only when the address names one, so Acoustic Bar's Ngô Thời Nhiệm is not covered.
* Legend search is one query per stop; its results vary run to run.
