# TASK LOCAL-442 — Sentence obligation ledger: every suggestion/mention/promise must be explained or followed

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-442-obligation-ledger`
**Base:** storied
(MUST be after the LOCAL-440 merge — this task edits the same generation
prompts; that is why it is PARKED. LEAD renames it into the dispatcher glob
when 440 has merged.)

## The defect class, in Michael's own words (2026-08-12)

> "I wonder if we should include assessment of every sentence to make sure the
> 'suggestions' or 'mentionings' of something are explained and followed later,
> because I see it all the time in our descriptions and I think we can get a lot of
> improvements if we do."

Confirmed direction: YES — this generalizes and replaces the one-species-at-a-time
deduction triggers (feel-telling, empty positioning, atmospheric filler are all
subspecies of one defect: **a sentence that writes a pointer and never dereferences
it**).

Canonical failing example, `TOUR_MFA_UNBOUND_20260812.txt` Stop 1:

> "As you approach Le Lézard aux plumes d'or (The Lizard with Golden Feathers) at the
> MFA in Boston, **position yourself to fully appreciate the interplay of color and
> form.** From this vantage, the vivid palette and intricate lithographic details
> emerge… **This positioning allows you to see** the flow of imagery as it was meant
> to be experienced…"

Three unfulfilled obligations in three sentences: an instruction with no position, a
promised vantage never located, a promised payoff ("flow of imagery") never
identified. History: "in front" was flagged for lacking a reason; the model's fix was
to keep the instruction and delete the content. The audit must make that evasion
impossible.

## What to build

### A. The auditor — `sentence_obligations.py`, module scope

`audit_stop_obligations(stop_text: str) -> dict` — ONE gpt-4o-mini call per stop
(temperature=0, SHA-256 verdict cache, same pattern as `story_gate.classify_story_unit`).
The call reads the WHOLE stop and returns a per-sentence ledger:

```
{
  "sentences": [
    {"sentence": "...", "obligation": "directive|reference|promise|significance|none",
     "missing_payload": "what the sentence points at but never delivers, or null",
     "fulfilled": true/false/null}   # null when obligation == "none"
  ],
  "unfulfilled_count": int
}
```

Obligation types:
- **directive** — tells the visitor to do something ("position yourself", "notice",
  "stand", "look", "approach"). Fulfilled only if the concrete where/what is in the
  sentence or adjacent ones.
- **reference** — mentions something specific-sounding without content ("the
  innovative technique", "his famous collaboration"). Fulfilled if the stop explains
  what/who/why.
- **promise** — asserts the visitor will perceive/gain something ("this allows you to
  see X"). Fulfilled if X is concretely identified.
- **significance** — claims importance ("remarkable", "masterpiece", "pivotal")
  fulfilled only if the stop supplies the evidence for the claim.

A sentence whose payload arrives elsewhere IN THE SAME STOP counts as FULFILLED — the
auditor sees the whole stop precisely so rhetorical setup paid off two sentences later
is not a false positive.

`audit_tour_obligations(tour_text: str) -> dict` — ONE call over the full tour for
cross-stop obligations: forward promises ("as we'll see later", "more on this at the
next stop", a person/theme introduced as important then dropped) with the stop where
each is (or is not) paid off.

### B. Generation side — Michael's repair loop (2026-08-12 session, BINDING)

After drafting each stop (in the LOCAL-440 story-first pipeline), run
`audit_stop_obligations`. Then per Michael's demonstrated procedure:

1. **Acceptable sentences STAY.** A sentence scoring paid/total ≥ 2/3 is kept as-is
   even with an unpaid obligation. Improvement is attempted only IF the paragraph
   has space remaining in the LOCAL-438 word budget (STOP_WORD_BUDGET=450).
   Sentences below acceptable (≤ 1/2 paid, or pure unpaid grandiosity like
   "reshape entire civilizations") are revise-or-delete candidates.
2. **Query construction from the unpaid claim:** substitute the work's name into
   the claim. Michael's worked example: "this work embodies the surrealist ethos
   of blurring reality and dreams" → "How do I see blurring reality and dreams in
   Le Lézard aux plumes d'or, Picasso, Miró, Dalí: Unbound exhibition, MFA Boston".
3. **Search order: SOURCES FIRST, then AI.** Fetch corpus/museum/Wikipedia sources
   for the payload; only if nothing is found there, ask the LLM (gpt-4o) — and an
   LLM-provided payload enters at web_search-tier provenance (trust 0.83/5) and
   MUST be corroborated by a fetched source before it is asserted in tour text
   (D373 Desnos rule; the same AI that wrote the empty gesture will happily
   generate its "explanation"). Visual claims checkable against the museum's own
   exhibition text are the preferred payload type.
4. **If a verified payload fits the space budget:** add the payoff, size-adapted
   (the D392 mechanism — summarize to fit). Re-audit; log before/after
   unfulfilled counts. Max two passes, then report honestly.
5. **If no verified payload or no space:** the acceptable sentence stays at 2/3
   and the unpaid obligation is logged as a story-seeking seed for LOCAL-440's
   query step.

**The anti-fabrication rule is the load-bearing constraint of this task.** Demanding
"explain it" without demanding sources reintroduces fabrication through the back
door. Any payload added by repair must be traceable to a fetched source.

**Michael's controversy rule (2026-08-12, BINDING):** verification outcomes map to
presentation modes, not only to scores:
- unverifiable → DROP;
- verified-false → drop, or narrate the correction if the error is itself the story;
- verified-DISPUTED (two real fetched sources genuinely disagree) → the story may be
  told AS the dispute, with attribution ("the museum's account says X, though …
  records suggest Y") — controversy is interest, and humans are intrigued by it;
- legend-tier → presentable honestly labeled ("legend has it…").
The dispute itself must be verified on BOTH sides. An invented controversy is worse
than an invented fact.

### C. Score side

`unfulfilled_count` per stop wired into the honest scorer as a deduction (LEAD will
calibrate the weight at review; propose one and justify it in the submission), so the
score index moves when prose gets emptier — Michael's requirement that the index
"represents our evaluation comparatively".

Keep D394 intact: the story-unit gate in `story_gate.py` is untouched as the unit of
STORY judgment. The obligation ledger is a separate axis.

## Michael's calibration rules (2026-08-12 session — BINDING, refines the above)

Michael hand-assessed MFA Stop 1 sentence-by-sentence and set these rules:

1. **In-sentence payment counts fully, and appositives are payment.** "Louis Broder,
   a notable figure who specialized in artist's books that required close
   collaboration between creators" — named AND explained right there: excellent.
   Do NOT demand citation-grade evidence for every adjective; that is pedantry and
   false positives.
2. **The ledger is CHAINED: a payment can open a new obligation.** "the surrealist
   ethos" is paid in-sentence by "of blurring reality and dreams" — which itself
   opens a new debt: HOW? Follow the chain until it closes or the stop ends.
3. **Grading, not gating.** Sentence score = obligations paid / obligations created.
   Paid anywhere in the paragraph = full credit for that obligation; never paid =
   that obligation only is lost (his example: 2/3 "acceptable", not zero).
4. **Unpaid hooks are story-seeking seeds.** "required close collaboration between
   creators" may be *stored for a possible story* — the ledger's unpaid items feed
   LOCAL-440's story-seeking queries rather than only being penalized.
5. **Definitional content counts as payment, even phrased abstractly.** "the
   seamless integration of image, word, and typography as an art form" IS the
   livre d'artiste definition — payload, not filler. The auditor must recognize
   the domain's definitions (the exhibition's declared art form, a technique's
   description) as payment. Do not penalize concept-explanation for not pointing
   at an object.
6. **Repair granularity is the FRAGMENT, not the sentence.** A below-acceptable
   sentence with one paying fragment gets REVISE-WITH-SALVAGE: the paying fragment
   survives, the unpaid grandiosity around it is fixed or cut. Whole-sentence
   deletion is only for sentences with zero paying fragments.

**Ground-truth worked example (fixture data), MFA Stop 1 description
(TOUR_MFA_UNBOUND_20260812.txt), Michael-assessed + LEAD-extended:**
- S1 "Published by Louis Broder…": Broder notability PAID in-sentence; surrealist
  ethos PAID in-sentence; "blurring reality and dreams" NEVER PAID → 2/3.
- S2 "Broder's editions… often involved…": pays S1 collaboration hook only
  GENERICALLY (no concrete interaction for this work); "coherent and integrated"
  never shown → 1/2 acceptable, keep. (MICHAEL-CONFIRMED 2026-08-12.)
- S3 "Mourlot Frères… 40 color lithographs…": concrete payload, best sentence;
  mild unpaid tail (which intentions, what precision) → ~2/2.
- S4 "…reshape not just art, but entire civilizations…": Michael-corrected to
  **1/3, not 0/2** — "the seamless integration of image, word, and typography as
  an art form" is the livre d'artiste DEFINITION and counts as payment (rule 5).
  Below acceptable → REVISE-WITH-SALVAGE (rule 6): the definition fragment
  survives; "reshape entire civilizations" is fixed or cut.
The auditor's output on this paragraph must substantially match this table,
including recognizing S4's definitional fragment as paid. See
LEDGER_CALIBRATION_S2_S4.md for Michael's verbatim comments.

## Acceptance fixtures (live gpt-4o-mini, exact)

1. **FIRES 3×** — Michael's Stop 1 quote above: the ledger must flag the directive
   (no position given), the promise ("allows you to see the flow of imagery" — flow
   never identified), and the vantage reference. `unfulfilled_count >= 2`.
2. **Does NOT fire** — same content with payload: "Stand at the left edge of the
   case, where the raking light picks out the overprinted gold layer on the lizard's
   feathers — Miró added it after the 1967 edition was destroyed." Expected:
   `unfulfilled_count == 0`.
3. **Reference species** — "The exhibition showcases his famous collaboration and the
   innovative technique that changed printmaking." with no elaboration anywhere in the
   stop → both flagged unfulfilled.
4. **Fulfilled-later-in-stop** — a stop whose first sentence promises and whose fourth
   sentence delivers → `fulfilled: true`, no false positive.
5. **Cross-stop** — a 2-stop mini-tour where Stop 1 says "we will return to Mourlot's
   workshop" and Stop 2 never mentions Mourlot → tour-level audit flags it; a variant
   where Stop 2 pays it off → clean.
6. **Revision rule** — given fixture 1's text and a fact sheet WITHOUT positioning
   facts, the revision pass must DELETE (not embellish) the positioning sentences
   (they are below acceptable: directives with zero payload). Verify no new named
   facts appear that are absent from the fact sheet.
7. **Repair loop (Michael's demonstration)** — given the S1 sentence ("…this work
   embodies the surrealist ethos of blurring reality and dreams", scored 2/3
   acceptable) and its stop: (a) the sentence is KEPT unmodified when the budget
   is full; (b) with budget available, the constructed query substitutes the
   work's name into the unpaid claim; (c) a mocked source returning the
   floating-forms/typography payload leads to a size-adapted payoff being added
   and the re-audit scoring S1 at 3/3; (d) the same payload offered ONLY by the
   LLM with no corroborating fetched source is NOT added, and the obligation is
   logged as a story-seeking seed.

## Evidence required (live-artifact gate)

- Live verdicts for all fixtures (not cached, not mocked) with per-call cost. Target
  ≤ ~$0.002/stop total added cost; report actual.
- One live MFA Unbound generation end-to-end with the audit+revision active; quote
  Stop 1's positioning/orientation sentences verbatim, and the before/after
  unfulfilled counts per stop. Env per D261/D262: `DISABLE_TOUR_CACHE=1`,
  `DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`,
  `STORIED_MODE=true`.
- Neutralisation proof per function (D242 #1): neutralise the auditor to
  always-fulfilled → fixture tests go red; neutralise revision to no-op → live-run
  assertion goes red.
- Tests in `tests/test_local442_obligation_ledger.py` using the LOCAL-439 pattern:
  live verdicts captured once, preloaded via a verdict cache for deterministic CI.

## PROCESS

- Work ONLY in your worktree on branch `LOCAL-442-obligation-ledger`.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`.
- Record reasoning in `SUBMISSION_LOCAL-442.md` at the worktree root.
- No `DELETE FROM audio_tours`, ever. Report row counts before/after for any table
  you write. Declare any live-DB change explicitly.
- Commit at least once (`git rev-list --count storied..HEAD >= 1`) — exit 0 without
  commits is a non-submission.
- "Unproven, handing to LEAD" is an acceptable report; an unproven claim stated as
  complete is not.
