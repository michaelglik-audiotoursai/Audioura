# My judgement on the verification tour of 2026-08-24, 22:59

Companion to **`TOUR_MFA_UNBOUND_20260824_2259.md`**. One generation, no selection. This is the
run that verifies LOCAL-465, LOCAL-466 and LOCAL-467.

---

## 1. Verdicts on the three tasks

| task | verdict | evidence |
|---|---|---|
| **LOCAL-465** exhibition not found | **works — after I fixed it** | see §2 |
| **LOCAL-466** more than one story | **works, and published none** | see §3 — the interesting one |
| **LOCAL-467** wrong gallery | **works** | no gallery asserted; Boris Fridman survives |

**The numbers are the best measured.** Stop index mean **75.7, range 73–81**. Every previous run:
67.8 (D515, 3 runs), 63.7, 69.7, 73.0. **The floor is the story — 73, against 44 three runs ago.**
All nine defect checks clean. $0.178, 550 s, 6,766 characters.

---

## 2. LOCAL-465 shipped broken, and its own tests could not have caught it

On the first live run the gate raised `NameError: name '_venue_entity' is not defined`, its
non-fatal wrapper swallowed the error, and **the fictional tour generated anyway — 7,331
characters.** Exactly what the task existed to prevent.

`_venue_entity` is a local of `_verify_works_v2`; the gate lives in a different scope entirely. It
had never worked, not once. Its 27 unit tests all exercised `resolve_request` in isolation against
fixtures and never touched the wiring, so they passed while the feature did nothing.

Fixed to use `_det_entity` — the resolved venue in that scope, the same object the D511 loop
reads. Both directions now verified live:

```
[LOCAL-465] EXHIBITION NOT FOUND: zero coverage: 0 COVERED, 6 candidates all
EMPTY/VENUE_ONLY — no content exists | request='exhibition blue green and silva in
MFA Boston, MA' | resolved=Museum of Fine Arts Boston (Q49133) | coverage=0/3
```

**No tour file written, exit 1.** And the criterion that mattered more — the real Unbound request
generated normally, which is this document.

**The lesson is about acceptance criteria, not about Kiro.** I wrote "returns NOT_FOUND and
generates no tour — show the log line and show that no `TOUR_*.txt` was written." That was the
right criterion and it was not met; I should have checked the submission against it before
merging rather than after.

---

## 3. LOCAL-466 works — and published zero second stories. That is the finding.

The code is correct and I verified it fires. What happened on all three stops:

| stop | candidates | accepted | second story |
|---|---|---|---|
| Le Lézard | 72, 73, **76**, 51 | 76 | #2 dropped (**+0 sentences**), #3 dropped (+1), #4 below the 55 bar |
| Moses | 25, 37, 63, **65** | 65 | #2 dropped (**+1 sentence**) |
| Au Soleil | …, **69** | 69 | dropped |

`+0 sentences` means the D518 merge absorbed the entire second story: **it said nothing the first
one had not already said.**

**So the answer to your question — "why did we not add another story to it?" — has changed.**
Yesterday it was "we bought four and binned three." Today it is: *we bought four, and three of
them are the same story told again.* The extra candidates are not extra material. They come from
the same object record, the same retrieval, the same handful of sources — so a different
credit_line mostly reorders the same facts.

**Adding length therefore needs diverse SEEDS, not more candidates.** A second story worth hearing
has to be about something the first one was not about — a different person, a different decade, a
different event. That is a retrieval problem, and it is the next real piece of work.

I would not raise `STORY_LOOP_MAX_STORIES` or lower `SECOND_MIN` to force a second story through.
The duplicate guard is currently the only thing standing between you and stops that say everything
twice, which is where this week started.

**One bug I found in review and fixed before merging:** LOCAL-466 merges each additional story
against text that already contains the previous one, and when that merge dropped the opening
sentence, D518b's "story becomes the opening" rule fired again and put the **second** story first —
weaker story leading, prose in the middle, best story last. `allow_story_first` now restricts that
rule to the first story.

---

## 4. LOCAL-467 — the gallery is gone, the donor survived

The 15:57 tour said the work was *"housed in the Linde Family Gallery"*. It is in the Torf Gallery.

This tour **names no gallery at all**, which is the acceptance criterion ("either it says Torf, or
it names no gallery"). And the criterion that mattered more — *"Boris Fridman still appears; a fix
that stops naming real donors has traded one defect for a worse one"* — holds: he is in the tour.

The chain that produced the error is closed at both ends: `Linde Family` is no longer classified
as a person, and the `pre_grounded_names` exemption now requires the beat's `source_work` to match
the stop it is used in, so an `exhibition_wide` beat can no longer ground a claim about one work.

---

## 5. A defect this tour shipped, and it is mine

Stop 3 reads:

> **"In 1916-1917, L. Gris's untimely death left Reverdy in a poignant position…"**

A mangled name welded to the wrong event — Gris died in 1927, not 1916-17. The story actually
retrieved was correct:

> "In 1916-1917, **L. Rosenberg** planned a book project with Juan Gris, who was to design it, and
> Pierre Reverdy, who would provide the text."

**My sentence splitter treated the initial `L.` as a sentence boundary.** That cut the sentence in
two; D518 then dropped the `"Rosenberg planned…"` half as a duplicate of the prose; and the orphan
`"In 1916-1917, L."` fused with whatever followed.

Fixed — the splitter no longer breaks after a single capital letter or after `Mr. Mrs. Dr. St.
Jr. Sr. vs. No. cf. ed. vol.` — and locked with tests including this exact sentence. **I did not
regenerate**, per your instruction; the tour above keeps the defect and this section names it.

**This is the sixth instrument failure today** and worth stating plainly, because the pattern has
not changed: check (a) demanded corroboration the worst case cannot provide; check (f) was anchored
to line start; the dedupe scanned only middle clauses; the missing-space repair could not cross a
quote; `ls -t` handed me a stale log; and now the splitter. **Every one was a rule fitted exactly
to the single example in front of me.** The tour passed all nine checks *and* contained a mangled
name, which is the honest summary of how much those checks are worth.

---

## 6. Where this leaves the product

**Good, and better than yesterday:** index floor 73, no duplication, no bracketed citations, no
spoken labels, no Treat Page, no invented gallery, no fictional tour for a request that matches
nothing. Every one of those was a real defect a week ago.

**Not yet good enough to ship**, for two reasons that are both about *material*, not mechanics:

1. **A stop still gets one story**, because the second candidate is the first one paraphrased.
   Length has to come from diversity of retrieval (§3).
2. **The instruments cannot tell a good tour from a mechanically clean one.** The rubric has read
   75.0 for seven consecutive runs across tours that differ enormously, including the fictional
   one. The stop index moves with real quality; the rubric does not. I would retire the rubric
   from these reports.

**Next, in order:** (1) seed diversity, so a second story is about something new; (2) three runs
under today's code, which is the first measurement that would mean anything; (3) the `L. Rosenberg`
class — check whether other truncated names are reaching tours.
