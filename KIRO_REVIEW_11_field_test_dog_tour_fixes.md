# KIRO_REVIEW_11 — Field-test fixes from "dog ridding tour, Big Lake, AK"

**From:** Claude (reviewer) · **To:** Kiro (executor) · **Date:** 2026-07-22
**Field test:** request `dog ridding tour, Big Lake, AK`, 3 stops requested, app log
`log_iphone_07222026_1812.txt`, job `b5378c4e-2ce4-488d-8c4e-05dafce9a927`, DB tours 6 (en) / 7 (ru).

**When done:** write your execution report to
`KIRO_RESPONSE_11_field_test_dog_tour_fixes.md` (same format as rounds 1–10:
per-issue what you changed, file:line, and how you tested). Claude will review
that document against the git diff before Michael approves. Do NOT commit —
leave changes in the working tree for review, same workflow as before.

---

## Issue 1 — Actual stop count is not persisted or surfaced (metadata says 3, ZIP has 2)

**Observed:** App saved `stops: 3` while the tour ZIP contains 2 audio files /
2 stops. DB row `audio_tours.id=6` has `stops_count = 0`.

**What already works:** `tour_orchestrator_service.py:736-764` already computes
`actual_stops` from the audio files in the ZIP, logs `STOP COUNT VERIFICATION`,
stores it in `ACTIVE_JOBS[job_id]["actual_stops"]`, and the status endpoint
returns it (`tour_orchestrator_service.py:1321-1324`). So detection exists —
persistence and propagation don't.

**Fix:**
1. Persist it: `store_audio_tour()` (`tour_orchestrator_service.py:304`) never
   writes the `stops_count` column that already exists in the `audio_tours`
   schema. Add `stops_count` to the INSERT (and the UPDATE path at ~line 466),
   passing the computed `actual_stops` down from the caller at ~line 803.
2. Ensure the **final `completed` status payload** always carries
   `actual_stops` (not only the in-memory path — check the DB-fallback path at
   ~line 1357 also includes it when the job is served from `job_status`).
3. Translation path: translated tours (e.g. tour 7) should inherit
   `stops_count` from the original row.

**Out of scope for this repo (note it in your response doc, don't fix):** the
iPhone app currently saves the *requested* count into its tour metadata. Once
the server reliably returns `actual_stops`, the app should prefer it — that's
an app-side ticket.

**Acceptance:** regenerate any tour where grounding drops a stop → the DB row's
`stops_count` equals the number of audio files in the ZIP, and the completed
status JSON contains the same number.

---

## Issue 2 — "dog" is not a recognized animal transport mode

**Observed:** `_detect_transport_mode()` returned `on_foot` for
`dog ridding tour` because the `animal` regex
(`generate_tour_text.py:64`) only knows `camel|horse`:

```python
'animal': re.compile(r'\b(camel(?:back)?|horse(?:back)?)\b(?:\s+\w+)?\s*tour\b', re.IGNORECASE),
```

Result: tour classified as walking even though the two stops are ~30 km apart
(Wasilla → Eagle River coordinates).

**Fix:** extend the animal alternation with dog/mushing vocabulary:

```python
'animal': re.compile(r'\b(camel(?:back)?|horse(?:back)?|dog|dogsled(?:ding)?|sled\s*dog|mushing|husky)\b(?:\s+\w+)?\s*tour\b', re.IGNORECASE),
```

Note the existing `(?:\s+\w+)?` modifier slot already tolerates the user's
"ridding" typo (`dog ridding tour` → `dog` + `ridding` + `tour`). Verify with a
unit test covering: `dog ridding tour`, `dog riding tour`, `dog sledding
tour`, `husky tour`, `mushing tour`, and a negative case like `dog park
walking tour` should still match animal (acceptable) — document whichever
behavior you land on.

---

## Issue 3 — Content title says "Walking Tour" instead of the transport mode

**Observed:** generated content header was
`... - Walking Tour` / `Tour-Category: walking`. For an animal-mode tour the
title should reflect the mode (e.g. `Dog Sledding Tour`), not the pedestrian
default. Michael prefers something like "Dog Riding"/"Dog Sledding" — use
**"Dog Sledding Tour"** when the matched keyword is dog/mushing vocabulary,
and generically derive the suffix from the transport mode otherwise
(`Camelback Tour`, `Horseback Tour`, `Cycling Tour`, `Driving Tour`).

**Fix:** where the content title/`Tour-Category` line is emitted, when
`transport_mode != 'on_foot'`, derive the display suffix from the transport
mode (and the matched keyword for the animal sub-type) instead of the generic
walking label. Keep `Tour-Category:` machine-readable (see Issue 4 — the
orchestrator will parse it); if you change its vocabulary, list the possible
values in your response doc.

---

## Issue 4 — DB tour name and translations still say "museum" (naming uses *requested* type, not effective category)

**Observed:** DB `tour_name` = `dog ridding tour, Big Lake, AK - museum Tour`,
and the Russian translation of tour 7 ends with «экскурсия по музеям» — even
though the generator corrected the category to walking inside the content.
The phone's tour list therefore shows "museum" forever.

**Root cause:** `tour_orchestrator_service.py:768`:

```python
tour_name = f"{location} - {tour_type} Tour"
```

`tour_type` is the raw value the app sent (`museum`), ignoring the effective
category the generator decided (line 2 of `tour_content`:
`Tour-Category: walking`).

**Fix:** after the tour content is available, parse the `Tour-Category:` line
(and/or the ` - <X> Tour` suffix of the content's first line) and build
`tour_name` from that instead of the request's `tour_type`. Fall back to the
requested type only if the content has no category line. Since the translation
service derives the translated name from `tour_name`, fixing it here fixes
translations too — verify with one ru translation.

**Acceptance:** regenerate the dog tour → DB `tour_name` ends with
`Dog Sledding Tour` (per Issue 3), and a requested ru translation contains no
museum wording.

---

## Issue 5 — Unknown/future transport modes (robots, drones, …): LLM fallback

Michael's requirement: camel/horse/dog are known today, but future requests
may say "robot riding tour", "drone tour", things we can't enumerate in a
regex.

**What already exists:** the intent-parsing LLM call
(`generate_tour_text.py:~250-300`, gpt-3.5-turbo) already returns a
`transport_mode` field, and the merge at `generate_tour_text.py:1551-1554`
already prefers the keyword match but falls back to the intent value. So the
"quick AI call" Michael asked about is **already in the pipeline** — it just
classified "dog ridding" as on_foot because the prompt's own description
biases it (`animal (camel, horseback)`).

**Fix (two parts):**
1. **Broaden the intent prompt** (`generate_tour_text.py:257` and the examples
   block ~282-284): change the `transport_mode` description to
   `animal (ANY animal-powered movement: camel, horseback, dog sled, elephant, etc.)`,
   and for vehicle add `(car, jeep, scooter, driving, or any motorized/robotic
   conveyance: segway, robot, drone-follow, golf cart)`. Add examples:
   - `"dog sledding tour near Big Lake, AK"` → `transport_mode: "animal"`
   - `"robot riding tour of the tech campus"` → `transport_mode: "vehicle"`
   - `"segway tour of Golden Gate Park"` → `transport_mode: "vehicle"`
2. **Guardrail:** if the request matches a generic "riding/back/sledding
   <word> tour" shape (e.g. `\b(\w+)(?:back)?\s+(?:riding|ridding|sledding|drawn)\s+tour\b`)
   but the keyword table found nothing AND the intent LLM said `on_foot`,
   log a warning line `[TRANSPORT] UNRECOGNIZED MODE CANDIDATE: <word>` so we
   can spot new modes in field-test logs and extend the table. Do NOT invent a
   new mode automatically — map to the intent LLM's answer.

Distance caps for unknown-but-classified modes fall through to the existing
`_TRANSPORT_TOTAL_HARD_KM` tiers — no change needed there.

---

## Issue 6 — Museum narrative register leaks into non-museum tours

**Observed:** the dog tour's stops are working kennels, but the narration says
"as you approach the … *exhibit*, position yourself at the edge of the
*viewing platform*", "this exhibit seamlessly integrates into the broader
context of *the museum*", "artistic, historical, and cultural significance"
(a verbatim phrase from the museum expansion prompt,
`generate_tour_text.py:2990-2993`).

**Root cause:** the per-stop expansion used the museum-style prompt because
the request's `tour_type=museum` (or the museum path was selected) even though
the effective category was walking/animal.

**Fix:** gate the museum expansion prompt on the **effective** category (the
same suppression signal as Touchpoint 1, `generate_tour_text.py:1632/1640`),
not the requested `tour_type`. When effective category is not museum, use the
general/outdoor narration prompt (no "exhibit", no "viewing platform", no
museum framing). Add a regression check: generated dog-tour text must not
contain the words "exhibit" or "museum" unless a stop genuinely is one.

---

## Issue 7 — Duplicated "Orientation:" field in stop text

**Observed (both stops):**
`Orientation: Head northeast on Knik-Goose Bay Rd… Orientation: As you approach…`

**Root cause candidates:** `generate_tour_text.py:3478` appends the literal
prefix `"Orientation: "` and lines ~3489-3499 append `f"Orientation: {orientation}"`
— when the LLM's own output also begins with `Orientation:` (its prompt at
~3192 asks for that header) the split at line 3231 either didn't run on this
path or the prefix got added twice. Trace the non-museum path and dedupe:
strip a leading `Orientation:` from the model text before prepending the
label, and make sure only one code site adds the label.

**Acceptance:** regenerated tour text contains exactly one `Orientation:` per stop.

---

## Issue 8 — Grounding quality flags (investigate, fix what's feasible)

From the same field test, for awareness and whatever is tractable this round:

1. **Fabricated person:** "Renowned artist and dog musher, Sarah McKinley" and
   her clay sculptures — no evidence this person exists. The
   no-fabricated-people constraint that exists on the museum path (cf.
   `generate_tour_text.py:3162` style constraints) should also apply to
   non-museum narration prompts: no named people unless they came from
   research/corpus input.
2. **Wrong location for a real venue:** Happy Trails Kennel (Martin Buser's,
   a famous Iditarod kennel actually located in Big Lake) was placed at an
   Eagle River address with Eagle River coordinates (61.2985, -149.5684).
   If coordinates verification can cross-check the POI name's canonical
   location, do it; otherwise note as known limitation.
3. **Invented directions:** "Lakeshore Drive… Mountain View Road… enjoy the
   scenic walk along Big Lake" between stops ~30 km apart. Once Issue 2 makes
   this an animal-mode tour, the directions prompt should speak in that mode's
   terms and must not describe a 30 km leg as a scenic walk. Check whether the
   directions template hardcodes walking phrasing.

---

## Test plan (run before writing your response doc)

```bash
cd ~/Audioura
python3 test_sq4_merge.py                      # must stay green
python3 test_palais_fix_lead_fixture.py        # must stay green
# rebuild + restart the touched services
docker compose -f docker-compose-master.yml build tour-generator tour-orchestrator
docker compose -f docker-compose-master.yml up -d
# regenerate the field-test tour and inspect
#   - content title / Tour-Category (Issues 2,3)
#   - DB tour_name + stops_count (Issues 1,4)
#   - no museum register, single Orientation per stop (Issues 6,7)
docker exec development-postgres-2-1 psql -U admin -d audiotours -c \
  "SELECT id, tour_name, stops_count FROM audio_tours ORDER BY id DESC LIMIT 3;"
```

Report results per issue in `KIRO_RESPONSE_11_field_test_dog_tour_fixes.md`.

---

# REVIEW VERDICT (Claude, 2026-07-22) — APPROVED with 2 follow-ups

All 8 issues verified against the actual code and database, not just the report:
regenerated tour 8 has title "Dog Sledding Tour", DB stops_count=2 (matches ZIP),
zero museum-register words, exactly one Orientation per stop, keyword=animal.
Both test suites re-run by reviewer: ALL TESTS PASSED.

Two items from the review were skipped without mention — fix before commit:

1. **Issue 1, UPDATE path:** `store_audio_tour()`'s UPDATE branch
   (tour_orchestrator_service.py:~455) still doesn't set `stops_count`.
   Regenerating an existing tour (same name+request) leaves a stale count.
   Add `stops_count = %s` to the SET clause.
2. **Issue 1, translation inheritance:** translated tours must copy
   `stops_count` from the original row (tour 7 shows 0). Fix wherever the
   translation row is inserted, and verify with one ru translation of tour 8.

Accepted as-is: `Tour-Category:` staying `walking` for animal mode (display
name and DB name are correct; vocabulary unchanged as permitted), Issue 8.2
deferred as known limitation.

Report the two fixes as an addendum in KIRO_RESPONSE_11.
