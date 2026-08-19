# Pending reminders for Michael

Durable across sessions. Delete a line once delivered.

- [x] DELIVERED 2026-08-07 12:4x — **Tell Michael to restart** once **LOCAL-354** (price band from guides) and
      **LOCAL-355** (practical facts for all venue kinds) are both reviewed and
      merged or bounced. He asked for this explicitly on 2026-08-07 ~12:00,
      having decided to clear at a natural break rather than mid-review.
      Practical steps to give him: `/clear`, then type `restart`.


- [ ] **⛔ 2026-08-18 21:49 — OPENAI CREDITS ARE EXHAUSTED. Only Michael can fix this.**
      Three measurement runs died at the first API call: `credit_balance_exhausted`,
      HTTP 429, nothing spent. **No tour can be generated at all** until credits are
      added at platform.openai.com/settings/organization/billing. This blocks the story
      work, every A/B, and the D480 3-run rule. Yesterday's spend was ~$3.13 / 16 runs.
      Consequence already recorded: **45.7 is stale, do not re-quote it** (A199, D483).

- [x] DONE 2026-08-18 21:4x — **Mission item 1 (audit the instruments as a class)** —
      D483, commit `36235ce`. `text_fold.py` is now the one folding primitive; 4 defects
      fixed across 3 gates; 60/60 new assertions, 21 red on revert. Items 2 and 3 were
      folded into the same suite (TRUE sets for every gate; the paired-instrument
      cross-check is section [5]). **Item 1's regex framing was slightly off** — all 42
      regexes were clean on boundaries; the bugs were in substring `in` comparisons.
      **Still open from that mission: the story-prompt extraction** — the one real
      quality lever, deliberately untouched, to be started with Michael awake and not in
      the same change as anything else (D474).

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
