# LOCAL-560 — Check/gate LLM calls on gpt-4o-mini; gpt-4o only where prose is WRITTEN

**Agent:** Mac Mini Kiro · **Branch:** LOCAL-560-checker-model · **Base:** fdbc779
(`git merge-base --is-ancestor fdbc779 HEAD` → 0)

This submission finishes LOCAL-560 **from the recordings** committed at fdbc779
(`tests/fixtures/local560/recordings/*.jsonl`, 8 real tours, every OpenAI chat call with
caller, model, messages, response, usage). The 8 tours were NOT regenerated.

**Michael's acceptance rule (verbatim):** *"get stops where discrepancy was found with the old
method and see if it is found with the new."* Decision rule per checker call site: switch to
gpt-4o-mini only if **recall on recorded discrepancy cases is 100%** (or a miss is proven to be an
old-model false positive, source text quoted) **and false alarms ≤ 10%**.

---

## §1 — Inventory of OpenAI call sites (from recordings + code grep)

Source: all 865 recorded OpenAI chat calls across the 8 tours (`recordings/*.jsonl`). "Model
today" is the model string **actually seen on the wire** in the recordings (which already
resolves every env fallback — all `TOUR_*_MODEL` were unset during recording, matching
production). Cost is computed from recorded `usage` tokens at `cost_rates.py` rates
(gpt-4o $2.50/$10.00, gpt-4o-mini $0.15/$0.60, gpt-3.5-turbo $0.50/$1.50 per 1M in/out).

Role: **WRITER** = output is prose the listener hears (or a phrase inserted verbatim into
narration). **CHECKER** = output is a verdict, score, list, JSON, classification, or extraction.

### CHECKER call sites

| Call site | Model today | Calls | In/Out tok | Old cost | What it decides |
|---|---|---:|---|---:|---|
| `stop_specificity_gate.py:433` | gpt-4o-mini | 279 | 99381/6550 | $0.3140 | Is the paragraph specifically about THIS stop vs a generic referent (specificity audit) |
| `story_gate.py:201` | gpt-4o-mini | 116 | 49404/7564 | $0.1991 | Is a candidate story-unit a real STORY (named person, actions, arc) — verdict |
| `unglossed_reference_gate.py:690` | gpt-4o-mini | 33 | 14346/3325 | $0.0691 | Triage named references: KNOWN_ENOUGH vs GLOSS_NEEDED (classification) |
| `fact_extractor.py:76` | gpt-3.5-turbo | 32 | 16872/5762 | $0.0171 | Extract verified facts from context → JSON |
| `generate_tour_text.py:1008` | gpt-3.5-turbo | 10 | 17001/1967 | $0.0115 | Intent analysis of the tour request → JSON |
| `generate_tour_text.py:9580` | gpt-3.5-turbo | 9 | 3522/4751 | $0.0089 | Stop ordering/selection → JSON array |
| `generate_tour_text.py:18583` | gpt-3.5-turbo | 7 | 7719/1721 | $0.0064 | Rank candidate facts by narrative interest → JSON |
| `generate_tour_text.py:1083` | gpt-3.5-turbo | 20 | 2261/681 | $0.0022 | Is "X" actually a restaurant → JSON verdict |
| `generate_tour_text.py:1577` | gpt-3.5-turbo | 5 | 1553/234 | $0.0011 | Geography fact-check: is the stop inside the bounded area → JSON |
| `story_element_extractor.py:419` | gpt-4o-mini | 1 | 377/19 | $0.0011 | Do two claims describe the same fact / agree → JSON |
| `theme_thread_discoverer.py:260` | gpt-4o | 1 | 444/1 | $0.0011 | Identify narrative themes connecting stops → JSON |
| `unsupported_claim_gate.py:452` | gpt-4o-mini | 1 | 242/4 | $0.0006 | Adjudicate claims against corpus (SUPPORTED/UNGROUNDED) |
| `generate_tour_text.py:9983` | gpt-3.5-turbo | 9 | 638/135 | $0.0005 | GPS coordinates for a stop (extraction) |
| `generate_tour_text.py:7770` | gpt-3.5-turbo | 5 | 1979/1719 | $0.0036 | List N real restaurants in area → JSON array |
| `generate_tour_text.py:8781` | gpt-3.5-turbo | 2 | 312/144 | $0.0004 | Suggest additional real restaurants → JSON array |
| `generate_tour_text.py:10105` | gpt-3.5-turbo | 1 | 183/34 | $0.0001 | Suggest 1 additional biking stop → JSON array |

CHECKER subtotal: **531 calls**, old cost ≈ **$0.6368**.

### WRITER call sites (models NOT changed in this task)

| Call site | Model today | Calls | In/Out tok | Old cost | Prose it writes |
|---|---|---:|---|---:|---|
| `generate_tour_text.py:14129` | gpt-4o | 100 | 710824/38793 | $2.1650 | Stop description (the main narration listeners hear) |
| `stop_knowledge_fallback.py:166` | gpt-4o | 25 | 27974/6305 | $0.1330 | Structure fallback prose into facts (feeds narration) |
| `restaurant_practicals.py:122` | gpt-4o | 18 | 22452/1728 | $0.0734 | Extract practical visitor facts (feed narration) |
| `spine_generator.py:165` | gpt-4o | 8 | 6543/5346 | $0.0698 | Narrative spine that threads the stops |
| `unglossed_reference_gate.py:1115` | gpt-4o-mini | 28 | 15459/557 | $0.0442 | Compose appositive gloss phrases inserted into narration |
| `unglossed_reference_gate.py:862` | gpt-4o-mini | 29 | 8242/1516 | $0.0358 | Supply factual gloss statements inserted into narration |
| `story_pass.py:295` | gpt-4o | 8 | 15948/961 | $0.0495 | The STORY paragraph for a stop |
| `generate_tour_text.py:20071` | gpt-4o | 5 | 4231/2425 | $0.0348 | Repair a section's factual defects (rewrites prose) |
| `generate_tour_text.py:15447` | gpt-3.5-turbo | 65 | 26840/5099 | $0.0211 | Style-violation rewrite of a paragraph |
| `generate_tour_text.py:18048` | gpt-3.5-turbo | 8 | 8418/1006 | $0.0057 | Tour prolog (intro prose) |
| `generate_tour_text.py:18726` | gpt-3.5-turbo | 10 | 5419/514 | $0.0035 | Preview sentence connecting intro to stops |
| `generate_tour_text.py:2044` | gpt-3.5-turbo | 7 | 2808/240 | $0.0018 | Recap clauses naming each stop |
| `directions_generator.py:331` | gpt-3.5-turbo | 17 | 4165/1022 | $0.0036 | Walking directions between stops |
| `story_leads.py:125` | gpt-4o | 4 | 914/461 | $0.0069 | Lead events for a stop (feeds story prose) |
| `restaurant_practicals.py:622` | gpt-4o | 2 | 444/196 | $0.0031 | Name real nearby restaurants |

WRITER subtotal: **334 calls**, old cost ≈ **$2.6512**.

**Total: 31 distinct call sites, 865 calls, old OpenAI cost ≈ $3.288 across the 8 tours.**

### Key findings
- The single most expensive site by far is the WRITER `generate_tour_text.py:14129` (stop
  description, gpt-4o) at $2.165 — 66% of all OpenAI spend. It is a WRITER and is **out of scope**.
- The biggest CHECKER spend is already on gpt-4o-mini (`stop_specificity_gate`, `story_gate`,
  the gloss triage) — $0.58 of the $0.64 checker total. These are the stops where discrepancies
  actually fire, so they are the critical recall targets.
- **gpt-3.5-turbo fallbacks fire for 14 call sites** (every `generate_tour_text.py` raw site,
  `fact_extractor.py:76`, `directions_generator.py:331`) because `TOUR_LLM_MODEL` is unset —
  confirming the ticket. Of these, the CHECKER ones (fact_extractor, intent, is-restaurant,
  geography, ordering, fact-ranking, coords, restaurant-listing) are the switch candidates;
  the WRITER ones (style rewrite, prolog, preview, recap, directions) keep gpt-4o-mini-or-better
  under WRITE_LLM_MODEL but are not re-pointed to a cheaper model.

(Replace fallbacks and switch decisions: §5 below.)

---

## §2 — Discrepancy cases (what the OLD checkers flagged)

A **discrepancy case** = a recorded CHECKER call whose verdict FOUND a problem. Decided purely
from each gate's recorded `response_text` using its own verdict grammar (confirmed from the
recordings and the `.log` outcome markers: `[LOCAL-472] UNGROUNDED`, `[LOCAL-229] BLOCKED`,
`DROPPED`, `is_story:false`, `GLOSS_NEEDED`, `inside_scope:false`, `DELETE:N`). Script:
`tests/fixtures/local560/mark_discrepancies.py` → `discrepancies.json`.

The specificity gate uses **two prompt variants** with different vocabularies (both decided from
the `VERDICT:` token only, never the free-text reason):
- NAMES variant: `GROUNDED` (clean) vs **`UNGROUNDED`** (flagged) — 100 UNGROUNDED
- SWAP variant: `SPECIFIC` (clean) vs **`TRANSFERABLE`** (flagged) — 10 TRANSFERABLE

**239 discrepancy cases** across 7 verdict-emitting checker sites:

| Checker site | Found / calls | Verdict that signals "found a problem" |
|---|---|---|
| `stop_specificity_gate.py:433` | 110/279 | VERDICT UNGROUNDED (names) or TRANSFERABLE (swap) |
| `story_gate.py:201` | 90/116 | `"is_story": false` |
| `unglossed_reference_gate.py:690` | 32/33 | `GLOSS_NEEDED` |
| `generate_tour_text.py:1577` | 4/5 | `"inside_scope": false` |
| `generate_tour_text.py:1083` | 2/20 | `"matches": false` |
| `unsupported_claim_gate.py:452` | 1/1 | `DELETE:N` (N≥1) / UNGROUNDED |
| `story_element_extractor.py:419` | 0/1 | conflicting / not-same-subject |

The 9 extraction/listing checkers (fact_extractor, intent, ordering, fact-ranking, coords,
restaurant/stop listing, theme discovery) emit no accept/reject verdict, so a single call cannot be
labelled FOUND vs CLEAN from its response. They are inventoried as checkers but excluded from the
recall denominator (no discrepancy verdict to miss).

---

## §3 — Replay with gpt-4o-mini

Every one of the **531 recorded CHECKER calls** was replayed against gpt-4o-mini with the same
messages, temperature, max_tokens and response_format, in a bounded thread pool of 8. Script:
`tests/fixtures/local560/replay_mini.py` → `replay_mini.jsonl`. **531/531 succeeded (status 200,
0 errors, 0 null responses).**

---

## §4 — Per-site comparison: recall, false alarms, cost

Script: `tests/fixtures/local560/compare.py` → `comparison.json`. Recall = of the OLD-model
discrepancy cases, how many gpt-4o-mini also flags. False-alarm rate = of the OLD-clean calls,
how many gpt-4o-mini newly flags. Costs from recorded/replay `usage` at `cost_rates.py` rates.

| Call site | Old found | Recall | Misses | False alarms | Old $ | New $ | PASS |
|---|---:|---|---:|---|---:|---:|:--:|
| `stop_specificity_gate.py:433` | 110 | **98%** (108/110) | 2 | 2% (3/169) | $0.3140 | $0.3143 | ❌¹ |
| `story_gate.py:201` | 90 | **100%** (90/90) | 0 | **15%** (4/26) | $0.1991 | $0.1995 | ❌² |
| `unglossed_reference_gate.py:690` | 32 | **100%** (32/32) | 0 | 0% (0/1) | $0.0691 | $0.0691 | ✅ |
| `generate_tour_text.py:1577` | 4 | 75% (3/4) | 1 | 0% (0/1) | $0.0011 | $0.0064 | ❌³ |
| `generate_tour_text.py:1083` | 2 | 50% (1/2) | 1 | 0% (0/18) | $0.0022 | $0.0120 | ❌⁴ |
| `unsupported_claim_gate.py:452` | 1 | **100%** (1/1) | 0 | n/a | $0.0006 | $0.0006 | ✅ |
| `story_element_extractor.py:419` | 0 | n/a | 0 | 0% (0/1) | $0.0011 | $0.0011 | ✅ |

Note: `stop_specificity_gate.py:433`, `story_gate.py:201`, `unglossed_reference_gate.py:690`,
`unsupported_claim_gate.py:452`, `story_element_extractor.py:419` are **already on gpt-4o-mini**
today — their old≈new cost confirms the replay reproduces the same spend, and the recall figure
measures determinism of the gate on the recorded inputs.

### Every miss (recorded discrepancy the new model did NOT reproduce), adjudicated

1. **`stop_specificity_gate.py:433` — 2 misses:**
   - `our_lady_help_newton` #58 — stop "Stained Glass Windows", names "Doherty".
     OLD: UNGROUNDED. NEW: GROUNDED. **Old-model false positive.** The source paragraph quotes the
     window's own inscription — *"May the Soul of William J. Doherty Rest in Peace," a tribute from
     Charles I. Doherty* — i.e. the entity is physically on THIS stop. gpt-4o-mini is correct;
     the old UNGROUNDED was the error. Excusable under Michael's clause (miss = old false positive,
     source quoted).
   - `our_lady_help_newton` #87 — stop "Stations of the Cross", names "St. Alphonsus".
     OLD: UNGROUNDED. NEW: GROUNDED. **Genuine miss.** The source only says St. Alphonsus's "1787
     version remains the most recognized in America" — it does NOT state that THESE stations are his
     version. The old UNGROUNDED was correct; gpt-4o-mini relaxed it. This is a real recall loss.
2. **`story_gate.py:201` — 0 misses, but 4 false alarms (15% > 10%):** gpt-4o-mini is *stricter*
   and rejects 4 story-units the old model accepted (Ebenezer Hancock; Legal Sea Foods;
   Tom Brady/Gisèle; William Turner viola). For a story GATE a false alarm = dropping a usable
   story, a content regression. Exceeds the 10% cap.
3. **`generate_tour_text.py:1577` (geography) — 1 miss (75% recall):** `buttermilk_bourbon` #92,
   "Saltie Girl". OLD: inside_scope=false (correctly out of scope). NEW: inside_scope=true —
   gpt-4o-mini trusted a plausible but **explicitly UNVERIFIED** address the prompt warned about.
   Genuine miss on a scope gate.
4. **`generate_tour_text.py:1083` (is-restaurant) — 1 miss (50% recall):** `sycamore_little_big`
   #7, "Sycamore". OLD: matches=false (ambiguous name). NEW: matches=true. Only 2 discrepancy cases
   exist for this site; one miss drops recall to 50%. Fails the strict rule on this recorded set.

### Extraction checkers (no reject verdict) — structural agreement
All 9 extraction/listing checkers (currently gpt-3.5-turbo except theme-discovery on gpt-4o)
produce **valid JSON on both models for every recorded call** (coords site emits Lat/Lng text,
not JSON, on both). So gpt-4o-mini is structurally drop-in for extraction, but there is no
discrepancy-verdict to measure recall against — they cannot be *proven* safe by Michael's rule.

### Cost headline
Old OpenAI cost across the 8 tours ≈ **$3.288**; CHECKER calls ≈ **$0.637** of that. The three
PASS sites are already gpt-4o-mini, so they yield **no new savings** — the real checker spend is
already on the cheap model. The gpt-3.5-turbo checkers that the ticket targets are small in
absolute cost ($0.047 total) and most are extraction (unprovable) or fail recall (1577, 1083).
The dominant spend is the WRITER `generate_tour_text.py:14129` (gpt-4o, $2.165), explicitly out of
scope.
