# SUBMISSION — LOCAL-618: The next critic blockers after work-first

**Branch:** `LOCAL-618-critic-blockers-2`
**Base:** `subscribed` @ `1aba2f5` (verified: `git merge-base --is-ancestor 1aba2f5 HEAD` → exit 0)
**Agent:** Mac Mini Kiro

## Summary

LOCAL-617 cut institutional sentences to 0–4% and the critic now reports "genuine
artist/work focus". This ticket's four named blockers are all fixed, each with a
pure deterministic module and offline tests, and verified in isolated metered live
runs. The headline live result: **Museum Boijmans — which clean-failed in LOCAL-617
(no tour at all) — now resolves to the museum and delivers.** The ≥6/10 bar is not
reached; the dominant remaining defect across all three museums is the pre-existing
LOCAL-617 recap/conclusion machinery (the trailing "That's N stops —" stub), which
is out of this ticket's four items and is reported honestly below, as 617 did.

---

## Item 1 — Stop-1 orientation no longer pre-tells the whole tour

**New module `orientation_pretell.py` (pure, deterministic, 7 unit tests).**
`strip_later_stop_facts` drops any orientation sentence that delivers a **later-stop
fact** — a year or proper noun that belongs to a stop ≥2 and not to Stop 1 itself —
while preserving the where-you-are sentence, the connecting thread, and the
"Your first stop is X" pointer. `build_forward_connection_prompt` is offered as a
thread-only replacement Part-4 prompt (no later-stop dates/names).

**Wiring:** `generate_tour_text.py` PHASE 5.96b, right after Part 4 folds into the
saved prolog. Guarded, never empties the orientation. The Part-4 forward-connection
builder (named in the ticket) is the exact source of the pre-tell; the guard runs on
its output so even if the LLM drifts, later-stop facts cannot reach Stop 1.

**Test:** `test_local618_orientation_pretell.py` — **7 passed**.

## Item 2 — deterministic grammar & splice lint on the final spoken text

**Extended `spoken_text_hygiene.py` (10 unit tests).** `flag_sentence` reports the
four defect classes the ticket enumerates, per sentence:
`'…-' splices` (the "Gertrud Dübi…-Müller" garble), **unbalanced** quotes/parens,
**verbless** fragments, and **repeated word pairs**. `grammar_splice_lint` DROPS the
flagged sentence, or hands exactly ONE flagged sentence to a cheap **metered** LLM
rewrite (`rewrite_fn` injected; the generator wires a `gpt` single-sentence repair
that owns its cost accounting). Counts are logged (`flagged/dropped/rewritten/by_code`).

Structured/practical lines (hours, prices, GPS, admission) are exempt so legitimate
data is never dropped — **calibrated to 0 false positives** on real delivered tours
(`tour_content_final.txt`, `tour214_content.txt`), the one residual flag being a
literal `+`-padding artifact, which is correct to drop.

**Wiring:** after `clean_spoken_text` in the finalization pass, metered rewrite_fn.

**Test:** `test_local618_grammar_splice_lint.py` — **10 passed**.

## Item 3 — venue resolution prefers the collecting institution over a sub-entity

**`venue_resolver.prefer_parent_institution` (pure, injected I/O, 8 unit tests).**
When candidates include a **P361 part** of another candidate, or a building/wing/depot
typed candidate, the sub-entity is collapsed onto the institution; survivors are
ordered by collection size (SPARQL work count, tie-broken by sitelinks). When the
largest collection **dominates** (≥10 works and ≥3× the next), it collapses to a
single winner so a downstream geo-disambiguation cannot re-pick a co-located wing.
Network-backed `_fetch_part_of_and_types` (P361/P31) and `_fetch_works_count`
(reusing `fetch_venue_works`) feed it. Wired into `resolve_venue` before geo
(guarded).

This is the Boijmans fix. The live log shows it working:
`[venue_resolver] #3 collection dominates (199 vs 1) — collapsing to Q679527` and
`Resolved: 'Museum Boijmans Van Beuningen' → Q679527` — the museum, not the
Robbrecht & Daem wing (Q134498261, 1 work). **The LOCAL-617 clean-fail is gone.**

**Test:** `test_local618_subentity_venue.py` — **8 passed**.

## Item 4 — honest hours line when the preflight returns none; never "check <domain>"

Two layers, so the honest line is both correct AND reaches every path:
1. `about_museum_stop._visiting_fallback_sentence` now returns
   **"Opening hours weren't published where we could read them."** instead of the
   dead-end "Check … on the museum's website before you go." The LOCAL-602 r2
   say-once collapse (`collapse_website_pointers`) and the LOCAL-615 fold regex both
   recognise the new wording, so it appears **at most once** tour-wide and real
   preflight hours still override it.
2. `practical_facts_gate.ensure_unpublished_hours_line` — a tour-wide pass in the
   every-path delivery guard. The first live runs showed the **fresh** museum path
   never built the About opening section, so Sevilla/Rouen spoke no hours at all.
   This inserts the honest line once (museum-gated; after paragraph-dedupe so it
   can't defeat duplicate removal; never when hours/a pointer are already present).

Live confirmation: Sevilla 441 and Rouen 442 each speak the line exactly once
(`unpublished-hours line count=1`), and **`'check…before you go' count=0`** on all
three.

**Test:** `test_local618_unpublished_hours.py` — **8 passed**. Three stale
LOCAL-592/616 assertions that encoded the old "check the website" wording were
updated to the new behavior (as LOCAL-616 did for its own wording change).

---

## Required test suites (exits)

```
test_local60*.py test_local61*.py test_local617_work_first.py \
  test_local590_*.py test_local592_*.py        exit 0   258 passed
tests/test_local60*.py tests/test_local61*.py  exit 0   308 passed
test_sq4_merge.py (as script)                  exit 0   ALL TESTS PASSED
test_local618_*.py (new)                       exit 0    33 passed
adjacent regression (529, d523, venue          exit 0    72 passed
  identity/class/reference, 282)
```

---

## Live runs — isolated container, metered, cap $2.50

Harness: `run_local618_live.sh` + `run_local618_container.py` — a disposable
`local618-gen` container (`--rm`, built from `Dockerfile.generator` on the branch
tree so ALL branch code is in the image), on `development_default` only to INSERT
additive `is_test` `audio_tours` rows for `critique.sh`. Tour cache OFF (fresh).
Metered + hard-capped at **$2.50 combined** via `tests/live_run_meter.py`. **No
DELETE.** Final run cost **$0.7329** combined (earlier runs $0.84 each, all under
cap). Tour IDs 440 (Boijmans), 441 (Sevilla), 442 (Rouen).

| Museum | LOCAL-617 | LOCAL-618 | Inst. share | Hours (#4) | Critic |
|---|---|---|---|---|---|
| Museum Boijmans Van Beuningen, Rotterdam | **clean fail (no tour)** | **DELIVERED** (Q679527) | 2% | real depot hours spoken | **3/10** |
| Museo de Bellas Artes de Sevilla | 3–4.5/10 | delivered | 0% | honest line ×1, no "check" | **4/10** |
| Musée des Beaux-Arts de Rouen | n/a | delivered | 2% | honest line ×1, no "check" | **4.5/10** |

Each item is observable in the live artifacts:
- **#3** — Boijmans resolves to the museum and ships a tour (was a clean fail).
- **#1** — Stop-1 orientations no longer carry later-stop dated events.
- **#2** — the lint runs on the delivered text (0 false positives on the clean body).
- **#4** — the honest hours line is spoken once; `'check…before you go'` is gone.

### Why ≥6/10 is not reached — the remaining blocker is pre-existing and out of scope

The dominant Critical/High defect on all three is the **trailing "That's N stops —"
recap stub**: it states the wrong count (3 when a late gate delivered 2), names only
some stops, splices per-stop metadata into a broken sentence, and stands in for a
real conclusion. The critic's three top code-level asks for every tour are the same —
"replace the recap with a real conclusion generator". This is the LOCAL-617
recap/conclusion machinery (`dedupe_conclusion`, `repair_truncated_tail`, the
shortfall-recompute class) and the fresh-path late-gate stop-drop — both named in the
LOCAL-617 submission as **pre-existing, separate systems**, not among this ticket's
four items. I did not expand scope into them; per the ticket ("report the remaining
blockers honestly, as 617 did"), they are reported here. A secondary, also-pre-existing
blocker the critic raised is that it treats the honest "weren't published" apology as
still failing criterion 3 (it wants real spoken hours) — the ticket's wording is
exactly what item 4 asked for, so this is an acceptance-bar tension to flag, not a
regression.

---

## Safety / constraints honored
- No DELETE (only additive `is_test` rows written by the live harness).
- No GCloud. No edits to DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md / STATUS.md.
- Branched from `subscribed` @ `1aba2f5`; every commit keeps `1aba2f5` an ancestor.
- All generator wiring is `try/except`-guarded and never empties a stop or breaks a working tour.

## Commits (one per item + two live-hardening + harness)
```
58dad4d #3: venue resolution prefers collecting institution over sub-entity
551066c #1: Stop-1 orientation no longer pre-tells the whole tour
22f1443 #2: deterministic grammar & splice lint on final spoken text
b0952ba #4: honest unpublished-hours line, never 'check <domain>'
761f366 isolated live-run harness (Boijmans/Sevilla/Rouen, 3 stops, cap $2.50)
8341e64 #3 (live hardening): collapse to the dominant-collection institution
95f4756 #4 (live hardening): say the honest hours line on EVERY museum path
```
