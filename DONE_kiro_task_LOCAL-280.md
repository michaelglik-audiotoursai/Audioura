**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-280
**Base:** storied
**Branch:** kiro/local280-closing-recap

# The tour should end by reminding the listener what they just heard.

Read `DECISIONS.md` **D181**, D184, D177, `tests/test_local44_stop_preaching.py`,
`generate_tour_text.py` (the closing block), the intrigue ranking added by
LOCAL-276.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## What Michael asked for

Reading the 8-stop round 31 closing:

> *"The last phraise does not promote Treats page and coming out of the blue.
> Also It feels we do need a conclusion, especially when number of stops is
> high, to remind listeners what they experienced and how 'well we did'."*

Current closing, which lands cold with no transition:

> "Place Masséna is 8 kilometers from here — we can build a cycling tour there.
> There is also a museum tour available at the Musee Oceanographique de Monaco.
> We can also generate news articles for you to listen to on the way back."

He drafted a version opening *"Thank you for taking Audioura tour, we hope you
enjoyed the experience."* **LEAD pushed back**: that thanks without reminding,
and is close kin to *"we hope you leave inspired by the beauty"*, which LOCAL-44
deleted and a regression test blocks. Michael agreed.

**His two rulings:**

1. *"let's replace the thank-you entirely"* — the recap **replaces** it, there is
   no thank-you sentence.
2. *"recap should be short, so when the listener took the tour of many stops, we
   should only choose the most interesting with the most facts we created for
   them. Obviously when user had only 2 stops, we should remind them about them
   briefly."*

## Scope

**Sentence 1 becomes a recap built from the tour that was actually delivered.**

Shape, from LEAD's proposal which Michael accepted:

> "That's eight stops and 92 kilometres, from a harbour in use before the Roman
> Empire to the village Louis XIV razed in 1706 — including the cell where the
> Man in the Iron Mask spent eleven years."

It states the scale, then names real content. It demonstrates how well we did by
**showing** the substance rather than asserting the listener enjoyed it.

### Selecting what goes in the recap

**Reuse what already exists — do not build a second ranker.** LOCAL-276 added an
intrigue ranking that classifies candidate facts as reversal / mystery / cause /
celebrity_trivia and excludes the last. The per-stop fact tally already exists
too. The recap is the mirror of part 4: part 4 previews, the recap concludes,
**same ranking, same verification**.

Scaling, per Michael:

| stops | recap |
|---|---|
| 2 | both stops, briefly — one clause each |
| 3–5 | scale + the top 2 by intrigue |
| 6+ | scale + the top 2–3 by intrigue; **do not list every stop** |

**Always state the scale** — stop count and distance — because that is the part
the listener cannot reconstruct themselves after eight stops.

### The rest of the closing

Sentence 2: the similar-tour offer and the capability offer, merged, with the
Treat Page. Sentence 3: news. Michael's corrections to the current wording:

- *"we can generate Musée Océanographique de Monaco"* is missing a word — it is
  a **tour of** it.
- **Treats wording reverts to the careful form.** His draft said *"look at
  Treats Page for coupons"*, which promises coupons exist. LEAD flagged it and
  he agreed. Use *"shows whether there are savings"* — his own earlier phrasing,
  and correct because we do not know what is there until the listener's location
  is queried.

**Total: 3 sentences.** The recap replaces the thank-you, it does not add to the
count.

## The line you must not cross

**Every fact in the recap must appear in the delivered text of the stop it
refers to** — the D177 rule, unchanged. Verify it and show the check. A recap
that misremembers the tour is worse than none.

**The recap describes what was delivered, not what was planned.** Take it from
the final gated text. Stops that produced no description must not appear — the
8-stop runs have delivered 6, 7 and 8 stops on different days.

**The three LOCAL-44 preaching tests must still pass.** Run them and show output.

| must FAIL review | must PASS |
|---|---|
| "Thank you for taking the Audioura tour, we hope you enjoyed the experience." | "That's eight stops and 92 kilometres, from a harbour in use before the Roman Empire to the village Louis XIV razed in 1706." |
| "We hope you found the journey inspiring." | "That's two stops — Monet's 1888 series at Cap d'Antibes and the 1306 chapel at Èze." |
| "look at the Treats Page for coupons" | "the Treats Page shows whether there are savings at local shops and restaurants around you" |

## Then regenerate

**2-stop** and **8-stop** Riviera tours, every gate on. **Copy both plain-text
files to `/Users/micha/Audioura/tours/`** — `tours/` is gitignored and worktree
artifacts do not survive the merge.

Report for each: the closing verbatim, sentence count, which stops the recap
named and why the ranking chose them, the D177 verification, words, generation
time, and cost against **$0.0185–$0.0206 / 43s** for 2 stops and **$0.0587 /
~118s** for 8.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Read the delivered tour as prose before reporting (D161).
- **D186:** the spine stays on gpt-4o. Do not change it.

## Acceptance criteria

- Recap replaces the thank-you; no thank-you sentence anywhere.
- Recap states scale and names real content, scaled by stop count as above.
- Selection reuses LOCAL-276's intrigue ranking, not a new one.
- Every recap fact verified present in its stop.
- Treats wording is *whether there are savings*, never that there are.
- "a tour of the Musée…", not "generate the Musée…".
- 3 sentences; 34 preaching tests pass.
- Both tours regenerated and copied to `~/Audioura/tours/`.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-280.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ⛔ BOUNCED by LEAD — 2026-08-05 17:36

**The machinery is right. The prose is not.** Keep everything structural; fix
what the recap actually says.

### What works and stays

- Thank-you gone; the recap replaces it. ✓
- Scale stated and honest — the 8-stop run delivered 5 and the recap says 5. ✓
- Treats wording exactly right: *"shows whether there are real savings"*. ✓
- Reuses LOCAL-276's `_recap_ranked_facts` rather than a second ranker. ✓
- D177 verification runs **and catches failures** — your own log shows
  `Recap: D177 FAILED for 'Fort Carré d'Antibes': fact not in delivered text`.
  That is the check working. ✓

### 1. The recap splices raw sentence fragments, not facts

Delivered 2-stop:

> "That's 2 stops and 18 kilometres — **Cycle along the coastline, carrying
> whispers of past revelries and the promise** and **Step into the Saint
> Charles-Saint Claude chapel**."

Three things wrong in one sentence:

- *"Cycle along the coastline…"* and *"Step into the…"* are **imperatives**.
  They are not facts and should never have been candidates. R1 exists to remove
  this shape from narration; the recap is pulling it back in.
- *"…and the promise"* is **truncated mid-phrase**. The extractor cut a sentence
  at a fixed length and emitted the stub.
- Two fragments joined with a bare "and" produce something no one would say
  aloud.

Delivered 8-stop is better but has the same class of fault:

> "That's 5 stops and 30 kilometres — The Carlton Hotel, an architectural gem
> designed by Charles Dalmas, and **the island is most famous for its fortress
> prison**."

Carlton Hotel / Charles Dalmas is a real fact and reads well. *"the island is
most famous for its fortress prison"* is lifted mid-sentence and **never names
the island** — the listener has no idea which of five stops is meant.

### The fix

The recap must **compose a clause**, not concatenate source text.

- Each recap item names **its stop** and the fact: *"the fortress prison on Île
  Sainte-Marguerite"*, not *"the island is most famous for its fortress prison"*.
- **Never emit a truncated span.** If a fact cannot be expressed whole in a short
  clause, choose the next-ranked one.
- **Imperatives and navigation are not facts.** Filter candidates through the
  existing checks before ranking — if `check_r1_imperatives` fires on a
  candidate sentence, it is not a recap fact. This is the same discipline part 4
  already applies.

Michael's target shape, which he accepted:

> "That's eight stops and 92 kilometres, from a harbour in use before the Roman
> Empire to the village Louis XIV razed in 1706 — including the cell where the
> Man in the Iron Mask spent eleven years."

Every item is a named thing at a named place, expressed as a clause.

### 2. Report the D177 failure rather than silently dropping

Your log shows Fort Carré failing verification. Good — but the submission should
state how many recap candidates were rejected and why, so the rate is visible.
If most candidates fail D177, that is a finding about the extractor.

### What to do

Fix the composition. Re-run both tours and paste each closing verbatim. Confirm
no imperative, no truncated span, and every item naming its stop.

Everything else in this task stays as merged-ready — do not rebuild it.

---

# ⛔ BOUNCED AGAIN by LEAD — 2026-08-05 18:38 (second bounce)

**Progress: the imperatives are gone and every item now names its stop.** That
was the main fix and it worked. The recap still splices raw source text rather
than composing a clause.

Delivered 8-stop:

> "That's 8 stops and 76 kilometres — Paloma Beach, **built a fort at
> Saint-Hospice in 1561 to secure**, Eze Village, seized under the command of
> Hayreddin Barbarossa, and Villefranche-sur-Mer, **established
> Villefranche-sur-Mer as a 'free port'**, enticing residents to settle by the
> coast."

Delivered 2-stop:

> "That's 2 stops and 14 kilometres — Vieux Village de Mougins, where **he**
> created intimate and profound works."

Four faults:

1. **Truncated spans persist** — *"built a fort at Saint-Hospice in 1561 to
   secure"*. To secure what? The previous bounce said explicitly: never emit a
   truncated span. This is the same defect in a new place.
2. **Dangling pronoun** — *"where **he** created intimate and profound works"*.
   Who? Presumably Picasso, but the recap never says so, and the listener has no
   antecedent because the clause was lifted out of its paragraph.
3. **The stop name repeats inside its own clause** — *"Villefranche-sur-Mer,
   established Villefranche-sur-Mer as a 'free port'"*.
4. **The 2-stop names only one stop.** The spec says both, briefly, at 2 stops.

### The root cause, stated plainly

Each recap item is still **a span cut out of a source sentence and pasted after
a stop name**. Cutting produces truncation; pasting produces the doubled name and
the orphan pronoun. No amount of better cutting fixes this.

**Compose the clause instead.** For each chosen fact, write a short noun phrase
that stands alone:

```
Paloma Beach, built a fort at Saint-Hospice in 1561 to secure   ->  the 1561 fort at Saint-Hospice on Paloma Beach
where he created intimate and profound works                     ->  the Mougins studio where Picasso worked
established Villefranche-sur-Mer as a 'free port'                ->  Villefranche-sur-Mer's founding as a free port
```

An LLM call is appropriate here and authorised — this is exactly the composition
job LOCAL-269 does for glosses, with the same constraint: **it may only rephrase
the supplied fact, never add one.** Batch all recap items into a single call.

### Verification that must still hold

- every recap fact still present in its credited stop (D177);
- no item exceeds ~12 words;
- no pronoun without an antecedent inside the recap itself;
- the stop name appears once per item, not twice;
- at 2 stops, both are named.

### ⚠️ You cannot verify by generation right now

OpenAI credits are exhausted — every generation returns
`credit_balance_exhausted`. **Do not burn a session retrying.** Build the
composition, unit-test it against the four strings above with the model call
stubbed, and say clearly in your submission that live verification is pending
credits. An honest "built, not yet verified end-to-end" is the correct
submission today.

---

# ⛔ BOUNCED — LEAD, 2026-08-05 22:5x (third bounce). One defect left, and LEAD has diagnosed it for you.

**The LLM composition works.** LEAD verified by live generation (credits are
restored) rather than on your mocked tests. Both tours generated cleanly:

```
2-stop:  47.3s  $0.0255   recap composition 1.3s  $0.0025  434 tokens
5-stop (8 requested)      recap composition 0.6s  $0.0025  428 tokens
```

Delivered 5-stop closing — **this is exactly right, do not change it**:

> "That's 5 stops and 48 kilometres — Cap d'Antibes, where Scott Fitzgerald
> wrote "Tender is the Night" and Eze Village, joined France in 1860 through
> unanimous vote."

Every item names its stop, carries a real fact, no truncation, no dangling
pronoun, no doubled name. The three defects from bounce 2 are gone. The closing
offer is correct too: "a tour of Place Masséna", Treats as *"shows whether there
are real savings"*, 3 sentences total.

## The one remaining defect

Delivered 2-stop closing:

> "That's 2 stops and 28 kilometres — Cap d'Antibes, **cycle towards Eze for
> medieval tales** and Eze Village, Louis XIV razed walls and castle in 1706."

The second clause is right. The first is an **imperative**, it is **navigation**,
and it describes a *different stop* than the one it is credited to.

### Root cause — this is not a composition bug

Your own log shows the LLM was handed the wrong source sentence:

```
[Cap d'Antibes] (cause): "Pedal along the coastal road from Cap d'Antibes
                          towards the fortified village of..."
   → composed: "Cap d'Antibes, cycle towards Eze for medieval tales"
```

That is the **Directions line**. The model rephrased faithfully; it was given
navigation and returned navigation. **The defect is in candidate selection.**

Bounce 1 told you to filter candidates with `check_r1_imperatives`. You did, and
it cannot work: **`_is_style_navigation_sentence` exempts navigation from R1**,
so a navigation sentence passes the imperative filter *by being navigation*. The
filter is structurally incapable of catching this class. That is LEAD's
instruction being wrong, not you ignoring it.

### The fix

**Exclude navigation from recap candidates explicitly, before ranking.** A
candidate sentence must be rejected if `_is_style_navigation_sentence(s)` returns
True — the opposite of how R1 treats it. Directions text is never a recap fact.

Also add, since D177 passed this through: **a recap clause must not name a stop
other than the one it is credited to.** "Cap d'Antibes, cycle towards Eze" names
Eze under Cap d'Antibes' credit. Reject and take the next-ranked candidate.

### Verification required

Regenerate **2-stop and 8-stop** and paste both closings verbatim. Confirm:

- no recap clause originates from a Directions or navigation sentence;
- no clause names a stop other than its own;
- the 5-stop closing quality above is preserved — that is the bar now;
- how many candidates were rejected as navigation, so the rate is visible.

## Also: filename collision, fix this

Your branch adds `run_round34.py`. **LEAD independently created a different
`run_round34.py` on `storied`** (for Michael's Riviera tour) and it is already
merged. Two different files, same name — this will conflict on merge.

**Rename yours to `run_local280_round34.py`** and keep its content. Do not touch
the one on `storied`.

## What not to touch

The LLM composition, the D177 check, the LOCAL-276 ranking reuse, the scaling
rules, the closing-offer wording, and the 5-stop output above are all correct and
merge-ready. This bounce is one candidate filter and one guard.
