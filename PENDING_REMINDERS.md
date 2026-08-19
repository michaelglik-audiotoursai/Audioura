# Pending reminders for Michael

Durable across sessions. Delete a line once delivered.

- [x] DELIVERED 2026-08-07 12:4x — **Tell Michael to restart** once **LOCAL-354** (price band from guides) and
      **LOCAL-355** (practical facts for all venue kinds) are both reviewed and
      merged or bounced. He asked for this explicitly on 2026-08-07 ~12:00,
      having decided to clear at a natural break rather than mid-review.
      Practical steps to give him: `/clear`, then type `restart`.

- [ ] **2026-08-18 10:2x — THE MISSION FOR THE NEXT SESSION, in Michael's words:**
      *"improve the validators so the good stories for humans are not dismissed as
      inaccurate when there is no evidence that they are."*
      **This is a false-positive problem, not a coverage problem.** The gates currently
      reject material that a reader would accept, on the strength of checks that do not
      actually establish inaccuracy. Two known instruments already lie and are the place
      to start, both unfixed: **D423** — `[LOCAL-410] beats_in_delivered_text` reports a
      false `0` while the beats are verifiably present in the text (LEAD nearly published
      "the gates are eating the stories" on that zero); and **D243/D462** — exact-match
      and identifier greps report false absence (accent-folding on `stop_corpus` joins;
      `other.pause()` vs `otherAudio.pause()`). **Before tightening anything, measure how
      often a gate's rejection is right.** The standing check applies with full force: run
      the gate against a case whose answer is already known. `story_validator.py`,
      `STORY_GATE_TIERS.md` and `story_lab.py` (D424) are the surface.
      Michael is driving this jointly — see the next reminder, which still binds.

- [ ] **2026-08-18 17:0x — THE MISSION FOR THE NEXT SESSION, decided from measurement:**
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

- [ ] 2026-08-12 20:5x — **DO NOT DISPATCH THE STORY PIPELINE. Michael is driving it.**
      He asked to work on story generation **jointly** in the next session, one
      subroutine at a time, using `story_lab.py` (D424). `PARKED_kiro_task_LOCAL-457.md`
      (strip the English gloss before queries are built) is deliberately parked for
      sequencing, NOT for approval — do not un-park it unless he says so, and do not
      write a new task that edits `generate_tour_text.py`'s story path in the meantime.
      RULE ZERO still applies to everything else.
- [ ] 2026-08-12 20:5x — **Start the joint session here:** open
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
