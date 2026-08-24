# My judgement on the Unbound tour of 2026-08-24, 15:57

Companion to **`TOUR_MFA_UNBOUND_20260824_1557.md`**. One generation, no selection.

---

## 1. Why the stories got fewer and worse — answered from the data

Your question: *"I see way less stories and less quality stories from iteration to iteration and
I wonder why."*

I did not guess. D514 has been persisting every candidate the loop buys to
`story_loop_candidates.jsonl` since 2026-08-23, so this is countable.

**Since D515, the loop bought exactly ONE credit_line per stop in 12 of 13 stop-attempts.**

Your rule says a story at index 50+ *"is the story and we do not need to verify more"*, and at a
floor of 50 the first candidate essentially always qualifies. So the loop stopped exploring. It
was not a gate problem and not a retrieval problem — the loop simply stopped looking.

Here is what the same three works score across runs, which is the part that makes it matter:

| work | indices observed |
|---|---|
| Au Soleil du Plafond | 64 · 50 · 71 · 73 · 78 · 60 · 72 |
| Le Lézard aux plumes d'or | 61 · 79 · 56 · 65 · 73 · 74 · 69 |
| Moses and Monotheism | 58 · 37 · 59 · 63 · 72 · 70 · 52 |

**A 20–35 point spread inside a single work.** Taking the first one over 50 is a single draw from
that distribution. Taking the best of four lands near the top. That is exactly "quality varies
from iteration to iteration" — it had become a lottery.

**And the second half of your sentence follows from the same cause.** `allowed_sentences()` maps
index to length: a story at 52 earns **three** sentences, a story at 74 earns **five or more**. A
low draw is not merely a weaker story, it is a *shorter* one. Fewer stories, in the literal sense
of less story text per stop.

### The fix, and what it does not change

The loop now examines up to four credit_lines and keeps the highest-scoring one, stopping early
only if something reaches 78 (`STORY_LOOP_STOP_AT`). **One clause of D515 changes and nothing
else** — the floor is still 50, `eventful` and `confirmed ≥ 3` still do not gate, a proven
factual error is still the only hard veto. "We do not need to verify more" becomes "we do not
need to verify more once we have something very good." `STORY_LOOP_BEST_OF=0` restores the old
behaviour exactly.

**It worked, visibly, in this run:**

| stop | candidates examined | accepted | would have shipped before |
|---|---|---|---|
| Le Lézard | 65, 64, 72, **77** | **77** | 65 |
| Au Soleil | 71, **76**, 69, 71 | **76** | 71 |
| Moses | (see log) | 63 | — |

**Stop index mean 73.0, range 63–83.** Every previous measurement, for comparison: 67.8 (D515,
3 runs), 75.7, 63.7, 69.7. The mean is the best measured, but the number I would actually trust
is the **floor**: 63, against 44 in the 12:23 run. The bad draw is what disappeared.

**It costs four times as much** — $0.178 per tour against $0.044, and 644 s against 325 s. That is
the real price of the fix and I am not hiding it. It is still under twenty cents a tour.

---

## 2. The other five tasks

| task | state |
|---|---|
| Duplication between sentences in one stop | **done** — the exhibition thesis may be stated once; a restatement carrying no new name, date or quantity is dropped |
| "Moses was an Egyptian priest" stated unopposed | **done** — a curated corrections table with a three-condition charter, never silent when it fires. Absent from this tour |
| `At this work:` template seams | **done** — the strip moved to where it sees the assembled tour. Absent |
| A different exhibition named as if you were in it | **done** — new check (g). Absent |
| Missing space after a full stop | **done, then found insufficient — see §3** |
| The two D515 amendments | **implemented, shipped OFF — deliberately, against my own earlier recommendation** |

**On the amendments I changed my mind and should say so.** I recommended them in D515. Both make
the gate *stricter*, and your observation plus the candidate log show the decline was caused by
**selection**, not by permissiveness. Turning them on would have cut the number of published
stories further, to fix a problem that was not there. They are one env var away
(`STORY_GATE_AMEND=1`) and should be measured after the selection fix has been measured, not
before.

---

## 3. Two defects in this delivered tour, one of them mine

### (a) The missing-space repair had a blind spot I built into it

This tour contains `…a harmonious blend of text and imagery.**"Au** Soleil du Plafond" thus
advances…`. My regex required two lowercase letters after the capital and could not cross a
quotation mark. `"Au"` has one, and the quote is in the way.

**The defect checker had the identical blind spot and reported the tour clean.** Both are fixed
and verified against nine controls (`christies.com`, `U.S.A.`, `Ph.D`, `www.mfa.org`, `e.g.`).

### (b) A preposition left holding nothing

> "The eleven lithographs, **housed in are** rarely on view…"

The log says why: `[LOCAL-392] Torf Gallery → DEGRADED (name dropped)`. An existing gate was right
to drop an ungrounded gallery name and wrong to leave the phrase dangling. Repaired, with check (i).

### (c) `"the Louis Broder Tériade"` is back — fourth sighting

Stop 2: *"the Louis Broder Tériade and Reverdy revived the unfinished endeavor."* Broder is stop
1's publisher. Base rate now **4 of 8 runs**. Nothing I have built touches it, because the error
is introduced when the descriptive prose is written and never adjudicated. This is now the
longest-lived unfixed defect in the tour.

**Note on timing, so the comparison is honest:** the fixes in (a) and (b) were committed *after*
this tour had assembled and *before* the second tour did. The second tour therefore had them and
this one did not.

---

## 4. What is good

**Stop 1's story is the best the system has produced,** and it cites the way you asked:

> Because the original lithographic stones had already been erased, Miró was forced to redraw an
> entirely new set of compositions from scratch. **While early catalogues claimed the entire flawed
> 1967 print run was destroyed, Sotheby's later revealed that impressions from the initial run
> survived in private collections.** Miró completed the brand-new series of plates four years
> later, finally releasing the finished edition in 1971.

Sotheby's is named **inside the sentence**, because the sources disagree — which is the exact rule
you gave me — and there is not a bracket in the tour.

**Stop 2 gained a fact no previous run had:** *"art dealer Léonce Rosenberg brought together
painter Juan Gris and poet Pierre Reverdy"*, plus the cause of death and his age. That is
best-of-four finding material the single draw never reached.

---

## 5. What I would still not ship

1. **Stop 1 is too long** — roughly twice stops 2 and 3. The thesis-restatement rule removed one
   sentence; several survive because they carry a new anchor (a gallery name, a number) while
   adding nothing a listener wants.
2. **`"the Louis Broder Tériade"`**, §3(c). Four of eight.
3. **The rubric base score has now read 75.0 for five consecutive runs.** It has stopped
   discriminating between tours that are visibly different. I would stop quoting it.

---

## 6. Next, in order

1. **Three runs under D523** — the first honest measurement of the selection fix. ~$0.55, ~30 min.
2. **The Broder/Tériade contamination**, four of eight and untouched by anything built today.
3. **Stop-1 bloat** — length caps per stop, or a stricter restatement rule.
4. **The `blue green and silva` finding** — see that judgement; it is more serious than anything
   here.
