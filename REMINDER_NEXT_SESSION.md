# READ ME FIRST — Michael's standing instruction, set 2026-09-23 20:10

Michael cleared the session at this point. He asked for ONE thing, and it is a
sequence — do not report until the whole sequence is done.

## The sequence

1. **Round 9 generation** — `run_round9.py`, log `round9_run.log`, output
   `TOURS_FOR_REVIEW/round9/`. It was RUNNING when he cleared. Confirm it finished:
   `ROUND9_SUMMARY.json` present and both `CHURCH_1.txt` / `LOGAN_1.txt` written.
   (He called this "loop #10"; on disk it is **round9** — same thing, the directory
   name is what to trust.)

2. **Then run the Amazon-Q / kiro critique on round 9.** Michael's standing rule:
   *"ALWAYS run Amazon-Q reviewer before asking for my review."* He is the LAST
   reviewer, never the first. Dispatch a critique task the usual way — write
   `new_kiro_session_is_required_LOCAL-NNN.md`, add the ID to
   `.continuous_dev/RELEASED.txt` (the allowlist now gates dispatch, D587), and let
   the tick claim it.

3. **Analyse the critique yourself. Do not take it as fact** — his words. Two
   critics have now been wrong: one called the Eiffel line a "boilerplate template
   paste" (there is no such template) and one undercounted Lindbergh's spread.
   Verify every quote against the tour file before acting.

4. **TELL MICHAEL when the critique comes back with nothing left to fix.** That is
   the signal he is waiting for — it means round 9 is ready for HIS review. If the
   critique DOES find things, fix them per his rule ("report to me, but do not stop
   to fix") and keep going; he does not want a report at every step.

## Context you need (full detail in SESSION_HANDOFF_20260923.md)

- Round 9 is the first batch generated with ALL round-7 fixes merged
  (D583/D584/D585/D586 + LOCAL-527/529/530/532). Same two venues as rounds 7 and 8,
  so the comparison is clean.
- **LOCAL-528 is COMPLETED with 1 commit and UNREVIEWED.** Verify it against the real
  jetbridge text before merging — LOCAL-532 shipped a defect that only hands-on
  review caught.
- **LOCAL-533** (instrument grounding cost) is released and pending.
- What still survives in round 8, and is the thing to check in round 9: fabricated
  attributions. Eiffel building Boston Logan; "Founded in 1868 by St. Mary Help of
  Christians" (the church's dedication turned into its founder); Lindbergh landing on
  a 1959 jet bridge in 1927. All scored CLEAN before LOCAL-527/528.

## Hardware answer, corrected after he replied

He has Dell/dock extensions with plenty of USB-C ports, **so the port-hub argument is
dead** and OWC's miniStack premium is not worth paying for. Recommend on capacity and
sustained write instead:
- ORICO MiniMate 4TB 40Gbps — https://www.amazon.com/ORICO-MiniMate-External-40Gbps-Plug/dp/B0DX5GBDXM
- Satechi USB4 Slim enclosure (bring your own NVMe, to 8TB) — https://amazon.com/Satechi-Enclosure-40Gbps-Sizes-2230mm/dp/B0FBBH35P8

Amazon renders prices client-side; the listings were verified live but **no price was
readable — do not quote one.** 2TB suffices for Docker volumes plus worktrees.
