# Pending reminders for Michael

Durable across sessions. Delete a line once delivered.

- [x] DELIVERED 2026-08-07 12:4x — **Tell Michael to restart** once **LOCAL-354** (price band from guides) and
      **LOCAL-355** (practical facts for all venue kinds) are both reviewed and
      merged or bounced. He asked for this explicitly on 2026-08-07 ~12:00,
      having decided to clear at a natural break rather than mid-review.
      Practical steps to give him: `/clear`, then type `restart`.


- [x] DONE 2026-08-24 10:4x — all four items. D518 (append), D519 (Treat Page), ONE tour
      delivered as `TOUR_MFA_20260824.md` + `TOUR_MFA_20260824_JUDGEMENT.md` (both opened in
      VS Code), three defects watched and all absent in this run. Full record D518-D520 / Q17.
      **Two runs happened: 10:26 exposed a defect in the append fix itself, 10:36 has the fix
      and is the deliverable even though it scores lower.** Original instruction below.

- [ ] **2026-08-25 — NEXT SESSION'S FIRST TASK: review and merge LOCAL-468, then measure.**

      **Read first:** `DECISIONS.md` tail (D518-D526), then
      [`TOUR_MFA_UNBOUND_20260824_2259_JUDGEMENT.md`](TOUR_MFA_UNBOUND_20260824_2259_JUDGEMENT.md),
      then Q22 in `STORIED_COMMUNICATION_03.MD`. That is the whole picture.

      **STATE AT THE /clear.** `storied` pushed and clean. In production: D518 (story replaces
      overlapping prose), D519 (Treat Page must be earned), D521 (no bracketed citations, no
      intra-sentence duplication, no spoken `Closing:`), D523 (best-of-4 selection; spoken-text
      hygiene; known-fact corrections), LOCAL-465 (exhibition not found — LEAD fixed a NameError
      that made it dead on arrival), LOCAL-466 (multi-story, works but publishes none — see
      below), LOCAL-467 (gallery attribution). Last tour: **index mean 75.7, range 73-81, the
      best measured; floor moved 44 -> 73.**

      **(1) LOCAL-468 IS COMPLETE AND UNREVIEWED** on branch `LOCAL-468-seed-diversity`
      (1 commit, `SUBMISSION_LOCAL-468.md` in its worktree). It is the fix for the thing Michael
      asked about on 08-25: four seeds naming FOUR DIFFERENT PEOPLE — Miró, Broder, Mourlot,
      Boris Fridman — all returned the same story about the 1967 paper defect. **The Mourlot
      answer never discusses Mourlot.** Causes, all three in `new_kiro_session_is_required_LOCAL-468.md`:
      the seed is a comma-appendage in `GEMINI_TEMPLATE`; `seed['ask']` exists in
      `_agent_seeds()` and production discards it (used only in the lab scripts —
      **the orphan pattern D511 was created to end, recurring inside D511's own module**); and
      prose seeds are subject-less fragments (`'was to design it'`).

      **Review it against its acceptance criteria, which are deliberately hard:** a live tour
      where stop 1's four candidates are about DIFFERENT things, pairwise overlap below 0.6,
      **and the indices must not collapse** (baseline mean 75.7, range 73-81) — a diverse set of
      weak stories is not an improvement.

      **VERIFY THE WIRING, NOT THE FUNCTION.** LOCAL-465 shipped with 27 green unit tests and a
      `NameError` on every live run, because every test called the decision function directly and
      none exercised the call site. Paste a real query showing `seed['ask']` reaching Gemini.

      **(2) THEN ONE TOUR.** Michael's standing rule: generate ONCE, never three-and-pick-the-best.
      Two documents in VS Code — the tour verbatim and LEAD's judgement.

      **(3) STANDING FINDINGS worth not re-deriving.**
      - **LOCAL-466 publishes one story per stop and that is CORRECT for now.** Its duplicate
        guard rejected every second story because they were the same story. Do NOT lower
        `STORY_LOOP_SECOND_MIN` or raise `STORY_LOOP_MAX_STORIES` to force one through — the fix
        is LOCAL-468, upstream.
      - **The rubric base score is dead.** 75.0 for seven consecutive runs across tours that
        differ enormously, INCLUDING a fictional one. Use the stop index; stop quoting the rubric.
      - **Six instrument failures on 08-24, all the same shape** — a rule fitted to the single
        example in front of it. Every new checker must be validated against a case whose answer
        is already known, in BOTH directions.
      - `"the Louis Broder Tériade"` cross-stop name fusion: **4 of 8 runs, untouched.** Longest-
        lived unfixed defect.
      - Michael on length: *"I am not bothered that Stop 1 is long… because of the stories not
        mere descriptions."* LEAD's "too long" recommendation is WITHDRAWN.

      **(4) Kiro auth expires.** All three tasks failed once on `OAuth error: Auth portal timed
      out` with zero commits. Michael logs in from a separate Kiro session; verify with a real
      headless call (`kiro-cli chat --trust-all-tools --no-interactive "..."`), not `whoami`.
      `FAILED` counts as claimed — append `ABANDONED` to `kiro_sessions_ran.md` to re-dispatch.

- [ ] **2026-08-24 — NEXT SESSION'S TASK LIST, Michael's instruction before /clear.**
      Do these in order. Everything needed is on disk; do not ask him to re-explain.

      **Read first, in this order:** `DECISIONS.md` tail (D511–D517), then
      `TOUR_MFA_FINAL_20260823_JUDGEMENT.md`. That is the whole picture.

      **STATE AS OF THE /clear (D517, all verified inside the running container):**
      the D511 story loop is ON by default, D515's acceptance rule is live at index 50,
      `GEMINI_API_KEY` now reaches the container, the image is rebuilt at the real HEAD,
      `storied` is merged with origin and pushed. Nothing is pending in production.

      **(1) FIX THE APPEND — this is the job.** `generate_tour_text.py:14209` is
      `description.rstrip() + ' ' + story`: plain concatenation. **Michael, 2026-08-24:**
      *"saying things twice is the worst for listeners — they hear that and get annoyed.
      Moreover, selecting the story topic based on the sentences made this problem so we
      need to fix it."*

      **Read that second sentence carefully — it is a design instruction, not a
      complaint.** The credit_line seeds are mined from the stop's own prose
      (`story_seeds.seeds_for_stop(stop_text, ...)`), so the loop is *guaranteed* to
      research whatever the prose already said, and then say it again better. The
      duplication is structural, not stylistic. **The story must REPLACE the prose it
      overlaps**, not follow it. Two measured examples in the judgement doc: Au Soleil
      tells Gris's death, the eleven plates and Mourlot twice; stop 3 says "Egyptian
      priest" in the prose and "Egyptian nobility" in the story — the corrected fact and
      the uncorrected one, kept side by side.

      **(2) FIX THE CLOSING.** Every tour ends with *"The Treat Page shows whether there
      are real savings at local shops and restaurants around here…"* — unconditional.
      Michael: **only mention the Treat Page if it is genuinely near a stop of the tour,
      any tour type, and it must not be the obligatory closing of every tour.**

      **(3) THEN GENERATE ONE TOUR. ONE.** Michael: *"have the one tour generated, not 3
      and take the best — this defeats the purpose completely."* No best-of selection.
      Put the tour and LEAD's evaluation in VS Code as two documents, as usual.

      **(4) THE THREE KNOWN DEFECTS — do NOT fix them now, but look for them in the new
      tour and say so if they appear.** Michael's ruling: fix only the append and the
      closing for now; if these persist, persist on them.
        (a) `"the Louis Broder Tériade"` — Broder is stop 1's publisher, Tériade is stop
            2's. **Reproducible across two runs, in two different generators** (the
            loop's sentence once, the descriptive prose once), so shared per-tour context
            is the suspect.
        (b) the priest/nobility self-contradiction inside stop 3 (fixed by (1) if (1) is
            done properly — check, do not assume).
        (c) missing space after a full stop (`depth.Boris Fridman`), third sighting.

- [x] DONE 2026-08-23 13:0x — **the A/B ran, the tour and LEAD's evaluation are in
      [`TOUR_MFA_20260823_LOOP_ON_EVALUATION.md`](TOUR_MFA_20260823_LOOP_ON_EVALUATION.md),
      opened in VS Code.** Six generations, arms alternating, 36 min, ~$1.1.
      **OFF 58.0 (sd 7.22) · ON 63.2 (sd 1.35) · +5.2, NOT significant** (Welch t=1.24).
      Drop the one bad OFF run and it is +1.0 — the loop prevented a bad run rather than
      improving good ones. Full record **D513 / A216**. Three blockers before release, and
      the loop is not one of them: an orientation that named the wrong artist for two of
      three works (1 run in 6), the story-append saying everything twice, and Moses
      publishing nothing 3 of 3. Original instruction kept below for the record.

- [ ] **2026-08-22 — NEXT SESSION'S FIRST TASK, Michael's instruction before /clear:**
      **regenerate the whole tour** `Picasso, Miro, Dali: Unbound exhibition at MFA,
      Boston, MA` **with all stories now in place**, write it to a document and open it
      in VS Code, then give LEAD's own evaluation of the tour and each stop.

      **Read first:** `ADJUDICATED_EVALUATION.md`, then `A213-A215` in `ANSWERS.MD`,
      then Q8-Q14 in `STORIED_COMMUNICATION_03.MD`.

      **What is in production** (D495, D498, D500 placeholder filter, D506's two bug
      fixes — the stop record now carries exhibition_name/printer/collaborator, and
      Gemini is no longer truncated to 60 chars).

      **What is NOT wired** and must be, or the tour will regenerate without any of
      this week's work: `story_seeds`, `story_relevance`, `story_query`,
      `story_adjudicate`, `story_publish_gate`, `object_record`, `story_hooks`, `story_roles`.
      Eight modules, no production callers. That is the same orphan pattern the
      7-step plan opened by complaining about — **wiring them is the job**, and it is
      what "with all stories now in place" means.

      **A213 is FIXED (D511):** the loop now seeds from the MATRIX AGENTS as well as
      the prose modifiers, so `agent:collaborator` = Sigmund Freud is a credit_line the
      pipeline can ask about even though the stop text never mentions him.

      **D512, both approved by Michael 2026-08-23 and landed:**
      (a) `material_kind` accepts the action and the stake in ADJACENT sentences that
          share a subject — requiring both in ONE sentence was measuring sentence
          construction, not story presence, and is why the Freud story scored `active`;
      (b) `domain_verbs.py` discovers the domain's verbs of making with ONE Serper
          query per tour (medium-led, page-fetched), widening `_AGENCY_VERB` — additive
          only, so a bad discovery can make the scanner generous but never blind.

      **THE RUN MICHAEL WANTS IS THE A/B, not a single pair.** He said a single
      old-vs-new comparison "gives me nothing as old can be random and so is new" —
      correct at sd 4.9 (D484). Three runs `run_full_tour_release_check.py` (loop OFF)
      and three `run_loop_tour.py` (loop ON), ~$1 and ~25 minutes total.

- [ ] **2026-08-19 — Boston Globe credential: MICHAEL DEFERRED TO THE WEEK OF 08-24.**
      His words, 12:2x: *"I do not have time this week so it will go to the next week."*
      `tests/run_mobile_decryption.py` carries `boston_username`/`boston_password` and the
      `device_key` that decrypts them, on origin since `ba6651b`. **Rotation is the only
      step that helps once pushed** — LEAD has not decrypted them and will not rewrite
      history (irreversible, Michael's call). See D223 / A-index.

- [x] ANSWERED 2026-08-20 — **source names delivered, recorded as D496.** Michael's order
      for art stories: (1) museum scholarly record — wall texts and `/objects/` collection
      pages, which carry production facts structurally; (2) artist foundation / catalogue
      raisonné; (3) livre d'artiste printer and publisher archives (Mourlot, Broder,
      Tériade, Verve, Maeght) — tier2, and only when `event=True`; (4) the art market,
      always −5, no lookup. **(4) is built (D495). (1)–(3) as retrieval PREFERENCE are
      not** — that is (c)/(e) and is where the next real gain is.

- [x] SUPERSEDED by the line above — **LEAD needed source names from Michael for D492(d).** The retrieval
      is reaching auction and dealer listings: the best action-bearing sentence in 112
      retrieved sentences was a lot description, another stop's was *"Sold as a set of
      10."* Naming 3–5 source TYPES he trusts for art stories (museum scholarly
      catalogues, artist foundation sites, exhibition essays, academic press) is worth
      more than any ranking heuristic LEAD invents, and is the one input that cannot be
      derived from the code.

- [ ] **2026-08-19 morning — READ THESE TWO FILES FIRST, they are open in VS Code:**
      `TOUR_MFA_RELEASE_20260819_0115.txt` and its `_MY_EVALUATION.md`. LEAD wrote the
      evaluation before you read the tour, so the comparison is worth something.

- [ ] **ONE DECISION IS YOURS AND BLOCKS NOTHING ELSE: which "story" definition wins?**
      Your step 3 says a chain ACROSS entities (fact → stop → exhibition). Your bar in
      `story_opportunity_scan` says THREE consecutive sentences about ONE person with an
      action and something at stake. A sentence each about publisher, printer and donor
      satisfies the first and is "a list of credits" to the second. The generator now
      aims at both; when the material supports only one, **which do you want?** See D485.

- [ ] **2026-08-19 — THE NEXT WORK IS RETRIEVAL, NOT PROMPTING.** With the story in its
      own pass, the limit is visibly the material: there are no stakes in the retrieved
      snippets for ANY stop, so the detector correctly refuses all three. Step 3.4's
      replenishment never fired because these stops are not thin by CHARACTER COUNT —
      they are thin IN KIND. The floor measures volume; what is missing is conflict.
      Do not spend another round on prompt shape. [D485]

- [x] RESOLVED 2026-08-18 22:0x — **OpenAI credits exhausted; Michael added $30, verified live.**
      Three measurement runs died at the first API call: `credit_balance_exhausted`,
      HTTP 429, nothing spent. **No tour can be generated at all** until credits are
      added at platform.openai.com/settings/organization/billing. This blocks the story
      work, every A/B, and the D480 3-run rule. Yesterday's spend was ~$3.13 / 16 runs.
      Consequence already recorded: **45.7 is stale, do not re-quote it** (A199, D483).
      **Top-ups are now logged in [`OPENAI_CREDIT_LOG.md`](OPENAI_CREDIT_LOG.md)** — Michael
      asked how much he added last time and nobody had written it down. Standing ask:
      **set auto-recharge**; the balance has run dry mid-session twice in two weeks.

- [x] DONE 2026-08-18 21:4x — **Mission item 1 (audit the instruments as a class)** —
      D483, commit `36235ce`. `text_fold.py` is now the one folding primitive; 4 defects
      fixed across 3 gates; 60/60 new assertions, 21 red on revert. Items 2 and 3 were
      folded into the same suite (TRUE sets for every gate; the paired-instrument
      cross-check is section [5]). **Item 1's regex framing was slightly off** — all 42
      regexes were clean on boundaries; the bugs were in substring `in` comparisons.
      **Still open from that mission: the story-prompt extraction** — the one real
      quality lever, deliberately untouched, to be started with Michael awake and not in
      the same change as anything else (D474).

- [x] DONE 2026-08-18 21:4x — **the instrument audit** (D483): one folding primitive,
      9 D243 sites, 70 assertions, 21 red on revert. Its own framing was slightly wrong —
      all 42 regexes were clean on word boundaries; the bugs were in substring `in`
      comparisons. Superseded by the retrieval mission above. Original text kept below
      for the reasoning, which still holds.

- [x] **2026-08-18 17:0x — THE MISSION, COMPLETED (kept for its reasoning):**
      Michael asked what the culprit of slow progress is. **It is that the instruments
      lie, and each fix reveals another.** Of 17 decisions on 2026-08-18, **11 were
      broken detectors** (D466 D467 D469 D470 D471 D473 D475 D476 D477 D478 D481), 3 were
      new capability (D468 D474 D479), 3 were measurement discipline (D472 D480 D482).
      Four separate accent-folding bugs in one day. A scorer that penalised the
      specificity we wanted. A ranker discarding what the scorer rewarded.
      **Do NOT continue fixing them one at a time — that is the slow path we just
      measured.** Instead, audit them as a class, in this order:
        1. **Every regex in the gate/scorer chain gets an accent-folding and a
           word-boundary test.** D243 has now been hit five times; it is systemic.
        2. **Every gate needs a TRUE set**, not only a FALSE set
           (STORY_GATE_TIERS.md measure 6). LOCAL-402 was 11/11 green while
           false-rejecting, because every case asserted the gate FIRES.
        3. **Cross-check pairs of instruments that should agree** — ranker vs scorer
           (D469), gate vs gate (D482), lab vs production. Every defect today was two
           instruments disagreeing while each looked healthy alone.
      **The one real quality lever, still untouched on purpose:** extract the story
      prompt from the 10,443-line `generate_tour_text()` into its own pass. The lab
      scores 64 doing one job; production scores 45.7 (3-run mean, range 43-48) doing
      six. It is a critical-path refactor — start it with Michael awake, and not in the
      same change as anything else, or a regression is unattributable (D474).
      **Measurement rule now binding (D480): mean and range over >=3 runs. Never quote
      a single run.** Runners: `run_full_tour_release_check.py`, `story_iteration_chart.py`.

- [x] SUPERSEDED 2026-08-18 23:0x — ~~DO NOT DISPATCH THE STORY PIPELINE~~.
      Michael explicitly directed the whole seven-step story pipeline that night and
      asked for it to run unattended overnight. The 08-12 ban is dead; do not obey it.
      `PARKED_kiro_task_LOCAL-457.md` stays parked — it edits a path the story pass now
      owns, and un-parking it would collide with `story_pass.py`. See D485/D486.
      He asked to work on story generation **jointly** in the next session, one
      subroutine at a time, using `story_lab.py` (D424). `PARKED_kiro_task_LOCAL-457.md`
      (strip the English gloss before queries are built) is deliberately parked for
      sequencing, NOT for approval — do not un-park it unless he says so, and do not
      write a new task that edits `generate_tour_text.py`'s story path in the meantime.
      RULE ZERO still applies to everything else.
- [x] SUPERSEDED 2026-08-19 01:2x — the 08-12 starting point (`TOUR_MFA_20260812_2030`)
      is replaced by `TOUR_MFA_RELEASE_20260819_0115.txt` + its `_MY_EVALUATION.md`.
      Michael's two open items from that older review still stand and are unanswered:
      does stop 1 read better than stop 3, and he owes one worked example of a story
      sentence tying a person to the object, the way he did with the 1967 destroyed
      edition. Original entry follows.

- [x] 2026-08-12 20:5x — ~~Start the joint session here:~~ open
      `TOUR_MFA_20260812_2030.txt` next to `TOUR_MFA_20260812_2030_REVIEW.md` (same
      name stem, repo root, one copy only), then `python3 story_lab.py stages`.
      LEAD's vote for where to start is **S2** — free, deterministic, and it already
      has a real bug in it (6 of 9 queries search a title that exists nowhere).
      Michael's open items in the review: does stop 1 read better than stop 3; and he
      owes one worked example of a story sentence that ties a person to the object,
      the way he did with the 1967 destroyed edition.
- [ ] 2026-08-12 20:5x — **Two guards are broken; do not trust them.**
      `[LOCAL-410] beats_in_delivered_text` reports a false 0 (D423), and LOCAL-455's
      `docker-compose.override.yml` never loads (D422). Neither has been fixed.
