# SUBMISSION — LOCAL-878

**Branch:** `LOCAL-878-evidence-geo-gate`
**Base:** subscribed (`8405e58d`) — `git merge-base --is-ancestor 8405e58d HEAD` exits 0.

Wave 36 re-proof (GCloud proof tour 547, gen 00038-qgw) failed three ways on
Michael's Saigon-centre 10-stop list. All three are fixed **at source**, with unit
tests, and one live 10-stop run in an isolated container.

---

## 1. Evidence must be at the pin (main bug)

**547:** stop "Opera House" (pin in District 1, HCMC) was narrated as the **Sydney**
Opera House (Utzon, Bennelong Point, 1973). The bare-name Wikipedia search returned
the Sydney article and `_name_ok` accepted it; LOCAL-855B's off-pin filter then dropped
only the one sentence naming a far place, so the rest of the Sydney article reached the
narrator and the claim gate.

**Fix — `landmark_wikipedia_evidence.py` (a true geo-gate, not another sentence filter):**

- `_default_fetch` now asks for each article's OWN coordinate and Wikidata item in the
  same call: `prop=…|coordinates|pageprops`, `coprop=type|name`, `ppprop=wikibase_item`.
  `_pages_from` carries `coord` (from `prop=coordinates`) and `qid`.
- `_geo_ok(pin, city, page)` is the gate:
  - **with a pin** — the article's coordinate must be within **`GEO_GATE_KM` = 2.0 km** of
    the stop pin (`_haversine_km`). If the article has no `coordinates`, a **Wikidata P625
    fallback** is fetched via its `wikibase_item` (`_p625_for_qid`). An article with no
    coordinate anywhere is accepted only when its title/lead **names the city**.
  - **no pin, but a city** — a coordinate-less article must name the city; a located one
    is accepted (no pin to refute it).
  - **neither** — no geo signal; accept (unchanged back-compat).
- **City-qualified retry:** when the bare name is rejected, `evidence_for` retries once
  with `"<name> <city>"` (e.g. `"Opera House Ho Chi Minh City"` → Saigon Opera House /
  Nhà hát Thành phố), matching the article against the **original** stop name
  (`match_name`), not the search string.
- **Rejected articles are cached as a MISS** for that `(name, pin-cell, lang)` — never as
  the venue's article (`_pin_cell` ≈ 1 km grid; the memo and DB keys both include it), so
  a repeat run never re-fetches Sydney for the Saigon pin and a same-name stop in another
  city is unaffected.
- City/alias handling: `_city_named` / `_city_tokens` treat **Saigon ⇄ Ho Chi Minh City**
  (and Hanoi ⇄ Hà Nội) as the same city. `_city_of(location)` derives the city from the
  tour location (first non-country comma part).

**Why 2 km:** wide enough to admit an article Wikipedia pins to a large complex's centroid
a few hundred metres from a specific gate, yet far tighter than any same-name place in
another city (the real refutation distances are tens to thousands of km — Sydney is
6,834 km from the District-1 pin). Override with `LANDMARK_WIKI_GEO_GATE_KM`.

**Threaded into the pipeline** (`generate_tour_text.py`): the stop's pin, parsed from
`poi['coordinates']` with `pin_snap._parse_coord`, is passed to `cached_evidence` at BOTH
call sites — the narrator block (~L23905) and the claim gate's parallel lookup (~L32567) —
so the one memoised lookup both share is geo-gated on the same pin.

**Tests:** `tests/test_local878_evidence_geo_gate.py` (10) — "Opera House" + HCMC pin gets
the Saigon article (or none), never Sydney; "Opera House" + Sydney pin still gets Sydney;
"Post Office" + HCMC pin gets the Saigon Central Post Office; a far post office is rejected;
a coordinate-less article needs the city name; `_pick` skips the far page.

## 2. Never empty when evidence exists

**547:** the Post Office stop shipped empty although evidence was "fed to the narrator".
Root cause was (1): the fed article was the wrong/off-pin one, so the evidence short-form
had nothing real. The never-empty machinery (`landmark_claim_gate.fill_empty_stops`,
D760) already regenerates an emptied stop from the evidence short form — it just needs the
**right** article. With the geo-gate (bug 1) feeding the Saigon Central Post Office, the
emptied stop is refilled from that evidence (`short_form` → 1886–1891, French colonial).

**Tests:** `tests/test_local878_never_empty_post_office.py` (4) — a Post Office stop whose
narration is dropped end-to-end (flagged) is refilled from the Wikipedia evidence
(`source == "wikipedia"`), never empty; `short_form` produces real sentences; the
geo-gated lookup feeds the right article to the fill.

## 3. The request string is not a place

**547:** the free-text request "Saigon centre landmarks, …" was taken as the locality —
narration said "in Saigon centre landmarks" and the city-context fetch hit
`/wiki/Saigon_Centre` (an office building).

**Fix — proper place-extraction, never the raw request:**

- `text_polish.city_from_scope` skips a leading free-text **TOPIC** segment
  (`_TOPIC_SEGMENT_RE`: landmarks / attractions / sights / highlights / spots /
  things-to-see / points-of-interest / best-of / top-N / hidden-gems / places-to-visit)
  and takes the next real place segment: "Saigon centre landmarks, Ho Chi Minh City" →
  **"Ho Chi Minh City"** (a topic-only string yields `""`, never the topic). The topic
  words deliberately exclude venue-kind words (museum/temple/church), so
  "Museum of Fine Arts, Boston" still resolves to the venue.
- `actionable_failure.derive_locality` drops a leading topic segment too (so the
  clean-fail suggestion locality is a place).
- `tour_conclusion.build_conclusion` (user-stops thread) runs `venue_name` through
  `city_from_scope`, so the closer reads "the places you chose across **Ho Chi Minh City**"
  (or "on this route" for a topic-only string) — never "across Saigon centre landmarks".
- `text_polish.place_location_for_title` + both live title builders
  (`generate_tour_text.py` ~L29888, ~L31293) drop a leading topic segment, so the title
  reads "**Ho Chi Minh City, Vietnam** - Walking Tour", not the request topic.

Because the locality is now the city, the city-context Wikipedia call resolves the CITY,
never `/wiki/Saigon_Centre`.

**Tests:** `tests/test_local878_locality_not_request.py` (8).

---

## Live proof (own container, D753)

`docker-compose.local878-proof.yml` (project `local878`, postgres on spare port **55978**,
own volume) — the shared `audioura-*` containers, the shared dev DB (:5433) and the live DB
are never touched. Generator runs in-process from this worktree so the run measures this
branch's code. TTS not called.

```
TASK_BUDGET_ID=LOCAL-878 TASK_BUDGET_USD=0.35 … python3 run_local878_live.py --saigon
```

**Result: 10/10 stops delivered; spent $0.2528 of the $0.35 cap.** Grep: `Sydney`,
`Utzon`, `Bennelong`, `Saigon centre landmarks` — **all absent** from the delivered text
(the two post-run fixes — the conclusion thread and the title — were then verified
deterministically against the exact delivered text rather than re-spending ~$0.25 of the
tight ~$19 OpenAI balance on a second run that carried no new signal).

First two sentences per stop (from the run):

1. **Notre-Dame Cathedral Basilica of Saigon** — "Orientation: This tour takes you from the Notre-Dame Cathedral Basilica of Saigon to Thi Bar Saigon … Your first stop is Notre-Dame Cathedral Basilica of Saigon."
2. **Saigon Central Post Office** — "Orientation: Its broad façade faces the square, bordered by Lê Duẩn Boulevard and Nguyễn Du Street … The building you see today was constructed between 1886 and 1891, designed by architect Auguste Henri Vildieu with assistance from Marie-Alfred Foulhoux during the French colonial era." *(not empty)*
3. **Nguyễn Văn Bình Book Street** — "Nguyễn Văn Bình Book Street is a cultural street in Ho Chi Minh City. It is known for numerous bookshops, cozy cafés, and regular literary events."
4. **Independence Palace** — "Orientation: Stand in front of the imposing north gates … The palace gardens offer a quiet green buffer …"
5. **War Remnants Museum** — "Standing before the War Remnants Museum, you see a building whose solemn presence contrasts with the bustling streets of Ho Chi Minh City …"
6. **Saigon Opera House** — "Orientation: Standing on Lam Sơn Square, your eyes meet the broad façade … The Saigon Opera House was opened on January 1, 1900, designed by the French architect Félix Olivier." *(the SAIGON opera house — French colonial, 1900; no Sydney/Utzon/Bennelong)*
7. **Ho Chi Minh City Hall (People's Committee Building)** — "Orientation: … the intricate Beaux-Arts details … The current seat of Ho Chi Minh City's government is a legacy of French vision from the close of the 19th century."
8. **Café Apartments, 42 Nguyễn Huệ** — "Orientation: Café Apartments is a unique café venue located at 42 Nguyễn Huệ, District 1, Ho Chi Minh City. The Café Apartments is a nine-story building originally constructed … around the 1960s."
9. **Bạch Đằng Pier** — "From here, your eyes can follow the boats gliding by … This spot frames the layers of Saigon's river life …"
10. **Thi Bar Saigon** — "Orientation: Thi Bar Saigon is a gay bar located at 224 Đề Thám, District 1, Ho Chi Minh City. Thi Bar Saigon is listed as a gay bar …"

Conclusion thread (after the fix, verified on the delivered text): *"Across these stops,
one thread runs through: the places you chose on this route …"* — no topic string.
Title (after the fix): *"Step-by-Step Audio Guided Tour: Ho Chi Minh City, Vietnam -
Walking Tour"*.

## Tests

150 tests pass across the touched modules (the 22 new LOCAL-878 tests plus the existing
872B/872C, conclusion, actionable-failure, title, and user-stop suites). Two unrelated
failures (`test_local585_r2` properly_cased_locality, `test_local592` admission_dollars)
pre-date this branch — confirmed by `git stash` on the clean base.

## Files

- `landmark_wikipedia_evidence.py` — the geo-gate (bug 1).
- `generate_tour_text.py` — thread the stop pin into both evidence call sites (bug 1);
  topic-safe title (bug 3).
- `actionable_failure.py`, `text_polish.py`, `tour_conclusion.py` — locality / conclusion /
  title derive a place, never the request topic (bug 3).
- `tests/test_local878_evidence_geo_gate.py`, `tests/test_local878_never_empty_post_office.py`,
  `tests/test_local878_locality_not_request.py` — the three bugs.
- `docker-compose.local878-proof.yml`, `run_local878_live.py` — the isolated live proof.

Run logs (`_local878_meterlogs/`) are not committed.
