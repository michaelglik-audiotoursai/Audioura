# SUBMISSION — LOCAL-663

**Branch:** `LOCAL-663-walking-v10`
**Base:** `subscribed` @ `4cc74f4d` (`git merge-base --is-ancestor 4cc74f4d HEAD` → 0)
**Agent:** Mac Mini Kiro

Two delivered defects on the Boston "Massachusetts politics and current affairs"
walking tour (tour 557 v10 / live tour 649):

1. **"The victims were Boston Massacre."** survived LOCAL-660's degrade guard.
2. **Faneuil Hall Stop 4 (1837 Lovejoy meeting)** shipped *"in late 1837, the
   hall hosted another turning point. The outcry in the hall was immediate"* —
   the event itself was gone.

Both fixed at the source in `tragedy_context_gate.py`, with regression tests,
a clean offline regression suite, and ONE paid live confirmation under cap.

---

## Bug 1 — "The victims were Boston Massacre."

### Where it comes from (why LOCAL-660 did not catch it)

LOCAL-660's copula guard (`unglossed_reference_gate._DEGRADE_GUARD_COPULA_BARE_ENTITY`
/ `_degrade_copula_equates_entity`) is correct, but it only runs **in the degrade
path**, gated behind a known `entity`. This sentence is **not produced by the
degrade path at all** — it is produced by the tragedy-context composer, so the
guard never saw it. That is why it survived.

The producer is `tragedy_context_gate._as_narration()`. After the gate recovers
a named death's circumstances (Michael's "search before you delete"), it checks
whether the recovered prose dropped any victim's surname and, if so, back-fills:

```python
missing = [n for n in (names or []) if n and n.split()[-1] not in txt]
if txt and missing:
    txt = txt.rstrip('.') + '. The victims were ' + ', '.join(missing) + '.'
```

`names` came from `_NAME_IN.findall(sentence)` — a bare *two-capitalised-token*
regex **with no filtering**. On the Boston Massacre stop the flagged death
sentence is:

> "On March 5, 1770, British soldiers fired into a crowd … in the Boston Massacre."

`_NAME_IN` matched **`On March`** (a date fragment) and **`Boston Massacre`**
(the event) as if they were victims. When the recovered narration did not repeat
the literal word "Massacre", the gate force-fed:

> "The victims were On March, Boston Massacre."

Reproduced offline directly against the regexes before any fix.

### The fix

Added `_is_person_name()` / `_victim_names()` to `tragedy_context_gate.py`. A
victim span is kept **only when every token is name-shaped** — structural, not a
lookup of names we have seen:

- the first token is not a preposition/temporal opener (`On`, `In`, `At`, `The`, …),
- no token is a month/weekday,
- no token is an event head-word (`Massacre`, `War`, `Riot`, `Battle`, `Party`,
  `Siege`, `Uprising`, …).

Applied at the source (where `_names` is built in `resolve_uncontextualised_deaths`)
**and** as a backstop inside `_as_narration` (so an unfiltered list passed by any
caller is still filtered). When no real person name remains, **no "The victims
were" sentence is emitted at all**. Real victims (D'Amore, Arpino, …) are still
restored, so Michael's narrow D577 exception is preserved.

```
victim_names("… in the Boston Massacre.")                 -> []          (was ['On March','Boston Massacre'])
_as_narration("Soldiers fired on the crowd.", <above>)    -> no copula   (was "… The victims were On March, Boston Massacre.")
victim_names("murder of Bruno D'Amore, … Lucia Arpino")   -> ["Bruno D'Amore","Gilda 'Jill' D'Amore","Lucia Arpino"]  (unchanged)
```

### Tests
`tests/test_tragedy_context_gate.py::TestVictimNameBackfillIsPeopleOnly` — 6 new
tests, including an end-to-end run through `resolve_uncontextualised_deaths`.

---

## Bug 2 — the 1837 Lovejoy event cut before it was told

### Where it comes from

`tragedy_context_gate.strip_uncontextualised_deaths` removes a **named violent
death that carries no nearby circumstance word** (Michael's rule: never name a
real person's violent death without its circumstances). On the Faneuil Hall
stop the death sentence was *"The abolitionist editor Elijah Lovejoy had been
killed, and citizens gathered here."* — no `_CIRCUMSTANCE` word in the window,
so the gate deleted it.

But the gate's orphan cleanup was **backward-only with a tiny hardcoded phrase
list** (`once again`, `in response`). It therefore left behind:

- the cataphoric **LEAD-IN** that announced the event: *"the hall hosted another
  turning point"* (it precedes the removed sentence — the backward sweep never
  looked there), and
- the backward **CONSEQUENCE**: *"The outcry in the hall was immediate"* (not in
  the hardcoded list).

Result: the stop teased an event and reacted to it, but never said what it was —
the exact delivered defect. Reproduced offline.

### The fix

Rewrote the sweep in `strip_uncontextualised_deaths` to be **position-aware**:

1. Capture the removed death sentences' **indices** first.
2. **Lead-in sweep** — drop an immediately-preceding sentence that is a bare
   cataphoric lead-in (`_CATAPHORIC_LEAD`: `another/a/the …
   turning point | moment | chapter | episode | confrontation | meeting | …`)
   that names no person (`_NAMED`).
3. **Consequence sweep** — the old explicit anaphors **plus** a generic
   definite-NP reaction subject (`_CONSEQUENCE_SUBJECT`:
   `The outcry/outrage/response/reaction/backlash/uproar …`), again only when
   the sentence names no one of its own.

Both are **gated on an actual death removal** and **adjacency-scoped**, so:

- a "turning point" lead-in that introduces its own following content and is not
  adjacent to a removed death **survives**;
- a stop with **no** uncontextualised death is **untouched** (ordinary prose,
  legitimate "turning point" / "The response" sentences survive);
- a **contextualised** death and its lead-in both **survive** (not removed);
- a standalone sentence that names its own subject ("Wendell Phillips rose to
  speak") **survives**.

```
strip("… another turning point. … Lovejoy had been killed … The outcry … was immediate. Wendell Phillips rose to speak.")
  removed: the death sentence + the lead-in + the consequence
  clean  : "Faneuil Hall has drawn orators for generations. Wendell Phillips rose to speak."
```

### Tests
`tests/test_tragedy_context_gate.py::TestEventRemovalTakesItsOrphans` — 7 new
tests covering the orphan removal, adjacency scoping, the no-death no-sweep case,
and the contextualised-death-survives case.

---

## Offline regression suite — GREEN

`tests/` set (unglossed 269, degrade 289, dangling 318, single-token 479,
verb-object 530, event-repeat 532, dangling-ref 538, walking v4 658,
walking v7/660, walking v9/662, 662b bounce, tragedy gate):
**249 passed, 2 skipped.**

Root-level set (623 stop-body defects, 624 narration splices, 475 gate-caused
corruption, 494 provenance-never-degraded, 479 org grounding):
**72 passed.**

`tragedy_context_gate.py` AST-parses; all public symbols intact. No regressions.

---

## Live confirmation — ONE paid Boston walking tour

Built `Dockerfile.generator` from this branch and ran it in a **disposable own
container** — `docker run --rm --name local663-gen -p 5121:5000 --network
development_default` (never `docker compose -p audioura`, never an `audioura-*`
container). Harness: `run_local663_container.py`, launcher: `run_local663_live.sh`.

ONE fresh paid tour (Boston "Massachusetts politics and current affairs",
5 stops, walking, NORMAL arm, cache + pool off). Deterministic detectors:

```
[PASS] BUG1_victims_were_event: copula_event_hits=[]
[PASS] BUG2_orphan_leadin_or_consequence: orphan_stops=[]
[LOCAL-663] BOTH DEFECTS GONE = True
STORED audio_tours id = 651  (is_test=true)
```

Stops delivered: Massachusetts State House, Boston City Hall, Boston Common,
**Faneuil Hall**, Old State House. The live Faneuil Hall stop told the 1854
Anthony Burns affair with its violent death **fully contextualised** ("the death
of deputy federal marshal James Batchelder" inside "Abolitionists … attempted to
free Burns … resulting in a violent confrontation"), so the tragedy gate
correctly **kept** it — no orphan lead-in, no dangling consequence. That is the
fix working in both directions: strip-with-orphans when uncontextualised, keep
intact when contextualised.

### Spend (from `paid_api_calls`) — under the $0.60 cap

- `paid_api_calls` host total after run: **$0.486953**
- tour `tour_total`: **$0.5201**
- `live_run_meter` breakdown (one `cost_ledger` row, `user_id=TEST-LOCAL-663`,
  `description='test run'`):
  - openai            $0.3048
  - gemini_grounding  $0.1960  (requests=5, queries=8)
  - gemini_tokens     $0.0182
  - serper            $0.0010
  - **TOTAL           $0.5201**

### Rows / safety

- **Additive `is_test=true` only.** My harness inserted exactly ONE row:
  id **651** (`is_test=t`). `is_test` row count 382 → 383.
- Row 650 (a Russian-language tour, `is_test=f`) is **not mine** — a
  translation-service artifact from another process; my harness only inserts the
  English `LOCAL-663 …` is_test row.
- **No DELETE.** No GCloud. Container and image removed on exit (`--rm` + trap).

---

## Files changed

- `tragedy_context_gate.py` — bug 1 (`_is_person_name`/`_victim_names`, applied at
  source + backstop in `_as_narration`); bug 2 (position-aware lead-in +
  consequence orphan sweep in `strip_uncontextualised_deaths`).
- `tests/test_tragedy_context_gate.py` — +13 regression tests (6 bug 1, 7 bug 2).
- `run_local663_container.py`, `run_local663_live.sh` — isolated live acceptance
  harness.

## Process

Committed after each step. `git rev-list --count origin/subscribed..HEAD` ≥ 1 at
every step. Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
`.continuous_dev/STATUS.md`.
