##### READY FOR REVIEW

**Task:** LOCAL-182 — Design the validation gate  
**Branch:** `kiro/local182-anchor-gate-design`  
**Commit:** `c44594e`  
**Base:** `storied`  
**Commits ahead of base:** 1

---

## Changes

| File | Action | Lines |
|------|--------|-------|
| `ANCHOR_GATE_DESIGN.md` | Created | +266 |

---

## Summary

Design document for the anchor validation gate. Recommends shadow mode
(log-only) first, with phased enforcement once corpus coverage reaches 60%
of stops on a tour. Key design decisions:

1. Gate runs inside existing content-QA stage (tour_generation_service),
   after rubric scoring, before TTS — no new container.
2. `UNLINKED_ENTITY` enforced first (more clearly wrong); `NO_ANCHOR`
   enforced later (generic but not misleading).
3. `NAVIGATION` paragraphs exempt — never scored or removed.
4. Search-before-remove pipeline: corpus → paid search → remove only if
   unfindable. Budget cap $0.10/tour.
5. Removal floor: never below 3 paragraphs per stop AND never more than 40%
   removed. Prevents thin tours.
6. When budget exhausted mid-tour: retain unresolved paragraphs, log them.
7. Three phases: shadow → selective enforcement → full enforcement, each
   with defined activation triggers.

---

## Verbatim evidence relied upon

**D51 — Michael's directive (search before removing):**
> "the default should be to find the reference even if we would require a
> different search through trusted sources that would cost us money… If we
> start simply remove everything we will end up with very little substance."

**D51 — Michael's directive (validation stage):**
> "I would make it on the validation stage — definitely before the user sees
> it — as we validate the content, we should also validate this as 'a fit'
> paragraph or a detail."

**D57 — Measured confirmation:**
> tour 29: 0.0% → 32.3% ANCHORED, spend $0.025, sources 15/15 stops

**D57 — The Fitzgerald result:**
> Wikipedia confirms Tender Is the Night is set on the French Riviera
> (tier 1). The paragraph classifies ANCHORED.

**D58 — Cost framing:**
> Users never see cost. They see limits.

**ClickUp wdvrdaxa7h — Michael's two tests:**
> Test: if you can substitute the names of places and say the same thing
> about another location, this paragraph is redundant.
> Test: if the paragraph mentions names or titles of books, movies, etc. it
> has to have some description how the person or the book or the seen
> relates to the Stop.

---

## Metrics referenced

| Metric | Value | Source |
|--------|-------|--------|
| Baseline ANCHORED (v1) | 19.7% | LOCAL-174 |
| Hardened ANCHORED (v2) | 4.2% | LOCAL-175 |
| With stop_corpus read | 6.6% | LOCAL-177 |
| Palais Lascaris after fetch | 23.5% | LOCAL-178 |
| Tour 29 after fetch | 32.3% | LOCAL-179 |
| Overall after all fetching | 13.2% | LOCAL-179 |
| Total loop spend | $0.041 | D57 |
| Noise floor | 0 (deterministic) | LOCAL-175 |

---

## Limitations

1. **No enforcement tested.** This is a design document. The proposed
   thresholds (60% corpus trigger, 3-paragraph floor, 40% cap, $0.10
   budget) are reasoned estimates, not empirically validated. They may need
   adjustment after shadow-mode data.

2. **The 13.2% baseline makes hard enforcement impractical today.** The
   design explicitly defers enforcement to avoid the "very little substance"
   outcome. If Michael wants faster enforcement, the corpus-building pipeline
   (LOCAL-178/179 pattern) must run first.

3. **"Generic but true" remains a judgment call.** The detector cannot
   distinguish "generic and empty" from "generic but atmospherically
   valuable." The removal floor mitigates over-pruning but does not solve
   the classification ambiguity.

4. **ANCHORED ≠ good.** The design document states this explicitly, but it
   bears repeating: a 100% ANCHORED tour can still be dull, repetitive, or
   poorly paced. The gate is one quality axis, not a complete quality system.

5. **Budget cap is estimated.** $0.10/tour is based on 5 rounds of observed
   costs ($0.002–$0.004/venue). If source APIs change pricing or the search
   pipeline becomes less efficient, the cap may need revision.

6. **No code was written or tested.** The implementation sequence in §7 is
   informational. Actual implementation will surface edge cases this design
   cannot anticipate.

---

## Constraints honoured

- [x] No code written
- [x] No gate enforced
- [x] No generation changes
- [x] No container work
- [x] $0.00 spend
- [x] Read-only against database
- [x] Detector unmodified
- [x] DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md untouched
