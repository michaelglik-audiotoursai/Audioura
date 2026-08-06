**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-286
**Base:** storied
**Branch:** kiro/local286-museum-part2-distance

# The tour opening treats a museum as a very small geographic tour.

Read `DECISIONS.md` **D167**, D190, `generate_tour_text.py` (the `[LOCAL-259]`
four-part prolog composition — the transport display map at ~line 7784, the
prompt at ~7844, parts 1 and 2 at ~7857), `tours/LOCAL282_museum_5stop.txt`.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.60**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**Check `.continuous_dev/PAUSE` before starting.** If it exists, OpenAI credits
are still exhausted and every generation will fail — build and unit-test the
change, state plainly that live verification is pending, and stop. Do not burn a
session retrying the API.

## The defect

From the museum tour delivered to Michael:

> "You are about to embark on a **walking journey** through the Musée des Arts
> Asiatiques in Nice, France. The route stretches from Les paysages de l'âme to
> Armure du Clan Hotta, **covering an approximate distance of 0 meters.**"

Two faults, one root cause. **The four-part opening was designed for geographic
tours and handles a museum as though it were a very small one.**

### Fault 1 — "walking journey" (part 1)

`_prolog_transport_display` (~line 7784) maps `transport_mode` to a word:
`on_foot`→walking, `bike`→cycling, `animal`→riding. A museum tour is `on_foot`,
so part 1's instruction — *"State the tour name and mode of transport"* — makes
the model announce walking.

Michael, reading it:

> *"I understand that when the means of transportation are other then human
> legs/feet the journey on Camels or dogs make sense, but in the museum,
> 'walking journey' sounds strange."*

He has drawn the right line. Naming the transport is **information** when it is
a camel, a dog sled, or a bicycle: it tells the listener what they are about to
physically do, and they may need to prepare. Inside a museum, walking is the
default — everyone walks in a museum. Stating it is not false, it is **empty**,
and empty sentences are exactly what LOCAL-263/272 exist to remove.

### Fault 2 — "0 meters" (part 2)

Part 2 states route physicality from the haversine between the first and last
stop. On the Riviera this works and is genuinely useful — LEAD verified 27.6 km
against a claimed "approximately 28 kilometres". **Inside a museum every object
carries the building's coordinates**, so the distance is correctly computed as
zero and then read aloud. The arithmetic is right; the question is wrong.

## Scope

**Parts 1 and 2 must say something true and useful for the tour's category.**

### Part 1 — drop the locomotion word where it carries no information

- **Keep it wherever the mode is not the default**: cycling, driving, riding,
  dog sled, road trip. Unchanged — this is the case where it informs.
- **Museum / indoor tours: do not announce walking.** Say what the tour actually
  is. The museum's name and the nature of the collection is the informative
  thing: *"You are about to explore the Musée des Arts Asiatiques in Nice"*, or
  a form the model composes from the venue. The wording is yours to propose, but
  the locomotion word goes.
- Do **not** simply swap "walking" for another generic verb across all
  categories — an outdoor walking tour of a city may legitimately keep it,
  because there the distance is real and the listener is choosing to be on foot.
  The test is whether the word tells the listener something they did not know.

### Part 2 — the whole sentence changes for museums

Michael, on the route sentence:

> *"I hope it is obvious that this has to change for Museum tours."*

It is not only the distance. *"The route **stretches** from X to Y, covering an
approximate distance of…"* is geographic language applied to a set of rooms.
**Rewrite the sentence for the museum case, not just the number.**

- **Geographic tours** (biking, walking, restaurant): keep the current
  behaviour — endpoints and distance. It works, and it is verified correct.
- **Museum tours**: distance between exhibits is meaningless and so is
  "stretches". Say what is actually navigable — the number of works, and floor
  or wing if the data supports it. *"Five works across the permanent
  collection"* is true and useful; *"0 meters"* is neither.
- **Never emit a zero or near-zero distance.** If the computed distance is under
  a sensible floor (say 50 m), omit the distance clause entirely rather than
  state it. That guard holds for every category, not just museums — any
  single-building tour will hit it.

## The line you must not cross

**Do not invent floor or wing data.** If `stop_corpus` or `venue_corpus` does
not record where a work hangs, do not guess — fall back to the count alone.
Inventing a location inside a building is the same class of error as inventing a
fact about the work (D127, D162).

| must produce | must not produce |
|---|---|
| museum part 1: the venue and its collection, no locomotion word | "a walking journey through the Musée des Arts Asiatiques" |
| museum part 2: "five works from the permanent collection" | "the route stretches from X to Y, covering an approximate distance of 0 meters" |
| cycling part 1: "a cycling journey" (unchanged) | locomotion dropped where it informs |
| Riviera 2-stop part 2: "approximately 28 kilometres of coastal terrain" (unchanged) | a distance under the floor, stated |
| single-building tour of any category: distance clause omitted | an invented floor or wing |

**Verify on all three categories** — museum, restaurant, biking (D190). Testing
only one category is what caused the museum overview regression this afternoon:
LEAD verified a prolog change three times, all on cycling tours, and shipped a
museum bug.

## Do not disturb what Michael has already approved

The four-part structure and its order are his, and part 4 plus `"Your first stop
is {name}."` were settled today after several rounds. **Change the wording of
parts 1 and 2 for the museum case only. Do not reorder, do not merge parts, do
not touch parts 3 or 4, and do not alter the geographic wording that works.**

## Then generate

A **5-stop museum tour**, a **2-stop Riviera cycling tour**, and a **3-stop
restaurant tour** if the selector permits. **Copy all plain-text files to
`/Users/micha/Audioura/tours/`** — `tours/` is gitignored and worktree artifacts
do not survive the merge; this has already handed Michael an empty file once.

Report part 2 verbatim for each, plus words, generation time and cost.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Read every delivered tour as prose (D161).
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria

- Museum part 1 does not announce walking; it names the venue and its collection.
- Cycling/driving/riding tours still announce the mode — unchanged.
- No zero or near-zero distance is ever stated; a floor omits the clause.
- Museum part 2 says something true about the tour's shape, and does not use
  "route"/"stretches" for a set of rooms.
- Riviera parts 1 and 2 unchanged and still correct.
- All three categories verified with the opening pasted verbatim.
- No invented floor/wing data.
- Parts 3 and 4 untouched; four-part order intact.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-286.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ADDENDUM — LEAD, 2026-08-05 22:1x. Two more prolog faults from round 34.

A 2-stop Riviera tour generated tonight
(`tours/LOCAL286_riviera_2stop_round34.txt`) shows two further defects in the
same paragraph you are already fixing. Both are in scope.

### 1. R7 sensory fabrication is reaching the prolog untouched

Delivered orientation:

> "As you stand on the rocky coastline of Cap d'Antibes, facing the **azure
> waters** of the Mediterranean Sea, the **sun-kissed peninsula** unfolds before
> you. The **salty breeze**, the sound of **waves crashing** against the
> **rugged cliffs**, and the **scent of pine trees** mingling with the sea air
> **stretches** out before you."

The R7 log line for this run reads `R7 summary: 0 sentences deleted, 0
paragraphs emptied, 0 stops affected` — while the text contains *azure waters*,
*sun-kissed* and *rugged cliffs*, which the spine prompt names explicitly as
banned and which `check_r7_hallucinated_sensory` is written to catch.

**Find out why R7 reports zero on this text and fix it.** The likely answer is
that PHASE 5.14 iterates stop descriptions and never sees the prolog, in which
case the prolog needs to pass through the same gate. Report what you actually
find rather than assuming this diagnosis.

Note also *"The salty breeze, the sound…, and the scent… **stretches** out"* —
plural subject, singular verb, and the sentence says nothing. It should not
survive R7 in any case.

**The exemption Michael confirmed is narrow.** He approved leaving *instructions*
in the Orientation ("enjoy the sea breeze") — that was about R1 imperatives. It
was never an exemption for fabricated sensory description. Do not widen it.

### 2. The prolog's last sentence is repeated verbatim in stop 1's body

Prolog: *"Pedaling away, the ancient cliffs of Cap d'Antibes hold echoes from
luminaries like Hemingway and Fitzgerald, while the building in
Saint-Paul-de-Vence was designed by Josep Lluís Sert…"*

Stop 1 body, last sentence: *"Pedaling away, the ancient cliffs of Cap d'Antibes
hold echoes from luminaries like Hemingway and Fitzgerald, blending history and
nature seamlessly."*

The listener hears the same clause twice within ninety seconds. Part 4 previews
the stops (LOCAL-270 composes it from delivered text) and the stop then repeats
it. **Deduplicate:** if part 4 has already used a sentence, the stop body must
not repeat it, or part 4 must draw from something the body does not end on.

Michael has been explicit about this class — *"we are not going to have two tour
descriptions"*. Add a check that no sentence of the prolog appears, at ≥8
consecutive words, anywhere in the stop bodies.

### 3. `Tour-Category: walking` on a cycling tour

`generate_tour_text.py:7725` writes `Tour-Category: {tour_category}` into the
header. Round 34 requested `tour_type="biking"`, the title line correctly reads
`- Cycling Tour`, and the category line reads `walking`. Downstream consumers
read that header. Fix the mismatch, and check whether the museum tour has the
same fault.

### Revised acceptance criteria — additional

- R7 fires on the prolog; the azure/sun-kissed/rugged-cliffs orientation above
  cannot survive a regeneration. Show the R7 log line and the delivered text.
- No prolog sentence repeats in a stop body at ≥8 consecutive words.
- `Tour-Category` matches the generated category on biking, museum and
  restaurant tours.
