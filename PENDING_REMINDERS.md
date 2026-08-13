# Pending reminders for Michael

Durable across sessions. Delete a line once delivered.

- [x] DELIVERED 2026-08-07 12:4x — **Tell Michael to restart** once **LOCAL-354** (price band from guides) and
      **LOCAL-355** (practical facts for all venue kinds) are both reviewed and
      merged or bounced. He asked for this explicitly on 2026-08-07 ~12:00,
      having decided to clear at a natural break rather than mid-review.
      Practical steps to give him: `/clear`, then type `restart`.

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
