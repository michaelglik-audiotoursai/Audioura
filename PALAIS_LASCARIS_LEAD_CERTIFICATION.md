# Palais Lascaris Fix — LEAD Certification Review

**Reviewer:** Claude (LEAD) · **Date:** 2026-07-14
**Commit under review:** `49c5a9a` — "Fix: thin-tier museums with sparse Wikidata no longer zero-stop-reject"
**Inputs:** `PALAIS_LASCARIS_FIX_REVIEW.md` (Kiro), `log_android_07142026_1220.txt`, `git show 49c5a9a` / `49c5a9a~1` into isolated /tmp (per LEAD rule — live tree untouched), deterministic logic fixture (8/8 assertions, see §5).

---

## 1. Verdict

**CONDITIONAL PASS — keep deployed, hardening required.**

- **Fix 3 (BLOCKER1 threshold): CERTIFIED.** Correct, minimal, provably the bug that turned "1 verified work" into a hard failure. Pre-fix, any 1-item POI list satisfied `0 >= 1//2 = 0` and was rejected with **zero** suspect venues. `max(1, len//2)` fixes exactly the pathological case and leaves all other list sizes unchanged (verified: thresholds identical for len ≥ 2).
- **Fix 1 (thin-tier candidate restore): CERTIFIED for the reported scenario, with 2 defects to fix** (§3, D1/D2). It unblocks generation and correctly orders verified works first; risk is bounded (fires only on `thin` + <3 verified + ≥3 candidates; BLOCKER4c QA still runs).
- **Fix 2 (R4 thin cap): MISCHARACTERIZED in Kiro's review.** It is unreachable in the Palais scenario (once Fix 1 fires, `len(poi_list) ≥ 4`, so `len < 3` is false). It only fires when GPT proposed <3 candidates, and its real effect is to silently un-gate the R4 replenishment loop for thin tier (previously rich-only per the code comment). Replenishment remains corpus-verified, so factual safety holds, but it adds up to 3 GPT calls for sparse venues that will mostly fail to verify. Not harmful; not what the review doc says it does.
- **Process: does NOT meet the "Delivered" bar** (§4). No committed wiring fixture, no committed pilot artifact with `code_sha`. Normally a bounce; given this unblocks the active mobile-testing mission, I recommend keeping it deployed and folding the fixture/artifact into the hardening task rather than reverting.

## 2. Root cause — certified failure chain

Confirmed independently from the committed pre-fix code (`49c5a9a~1`):

1. PHASE 3A proposed 7 candidate works; venue resolved via Wikidata (thin evidence).
2. **D1v2 dropped 6/7 candidates** — "no canonical title match." Important precision: the canonical set is NOT Wikidata-only; it is the **union of Wikidata SPARQL works + official-site extraction + Wikipedia extraction** (`_verify_works_v2`, ~lines 690–740). For Palais Lascaris all three sources together yielded essentially 1 title, so the union didn't save it. Kiro's framing ("must be in Wikidata's listing") understates the sources but the substance stands: **each stop had to appear in some external listing, and small-museum coverage in all three sources is sparse.**
3. R4 capped `total_stops = 1` (thin tier → verified only).
4. **BLOCKER1 rejected the 1-stop list with zero suspects** (`0 >= 0`) → `return None`. This — not D1v2 — is the proximate cause of the hard failure; without it a 1-stop tour would have been produced.
5. Service mapped `None` → "no stops could be generated." Note: BLOCKER1/BLOCKER4b return `None` **without setting `_LAST_CLEAN_FAIL_EVIDENCE`**, which is why mobile showed the generic message with `Type: null` instead of the LOCKED structured clean-fail. Contract gap (task filed).

Both failing requests behaved identically because both resolve to the same QID; the second attempt's different spelling changed nothing.

## 3. Defects found in the fix (hardening required)

**D1 — Fix 1 restores REJECTED (wrong-venue) candidates.** `_unverified` is built as "all pre-D1v2 candidates minus verified names." D1v2's evidence log distinguishes `VERIFIED` / `DROPPED (no match)` / `DROPPED (duplicate QID / theme word / cycle name)` / **`REJECTED (located at <other venue>)`**. The restore ignores these statuses, so a candidate with positive evidence of hanging in another museum gets restored — reintroducing exactly the hallucination class D1v2 exists to block. Fixture assertion D1 demonstrates it. **Fix:** restore only candidates whose evidence status is `DROPPED/no canonical match`.

**D2 — Canonical-rename creates duplicate stops.** D1v2 rewrites a verified POI's name to its canonical title (`poi['name'] = _best_title`). Fix 1 then compares by raw `.lower()` of the ORIGINAL candidate names, so a work verified under a variant name ("The Raquel Portrait" → "Raquel") no longer matches and is re-added as a second, unverified stop of the same work. Fixture assertion D2 demonstrates it. **Fix:** exclude by evidence-log key status (the log is keyed by original candidate name), or compare with `_normalize_name` against both original and canonical forms.

**D3 — Report-accuracy / cosmetics (fold into same commit):**
- Fix 1's log line prints `len(_pre_d1v2_candidates)` ("restoring 7") though it restores `min(5, unverified)`. Kiro's review quotes "restoring 6 GPT candidates" — that string cannot be produced by this code for a 7-candidate run. Recurring mischaracterization pattern; verify the actual container log.
- R4 else-branch now prints "capped to N **verified** works" when the list contains restored unverified works.
- Restored stops carry no `unverified` flag downstream: narration can't hedge ("attributed to…", "visitors report…") and `stop_metrics` can't distinguish verified from trusted-GPT stops. For Subscribed's forecasting this distinction is data — tag it now (`poi['verified'] = False`), even if narration hedging lands later.
- Pre-existing nit surfaced by fixture T4: `_VENUE_INDICATORS` misses accented forms (`opéra`, `théâtre`) so BLOCKER1 undercounts French suspects.

## 4. Process compliance (binding rules §0c)

| Rule | Status |
|---|---|
| Delivered = call site + wiring fixture | ✗ no fixture committed (commit touches 1 file) |
| Pilot evidence committed with `code_sha` | ✗ "10,425 chars / 6 stops" claim is unreproducible — nothing committed |
| Review doc in git | ✗ `PALAIS_LASCARIS_FIX_REVIEW.md` untracked |
| Regression guardrails | Not run by LEAD (needs live keys); fixture T3 confirms medium/rich logic paths byte-identical pre/post fix, so SQ4/W7/W9 exposure is nil by construction |

Live tree note: `generate_tour_text.py` working-tree diff vs `49c5a9a` is pure CRLF noise (`git diff --ignore-cr-at-eol` = empty) — the committed code IS the running code. Verified.

## 5. LEAD fixture

`test_palais_fix_lead_fixture.py` (this directory) — deterministic, no network, replicates the exact post-D1v2 logic pre/post fix. 8/8 assertions: T1 reproduces the pre-fix zero-suspect rejection; T2 fixed path yields 6 stops/passes; T3 medium tier byte-identical behavior; T4 BLOCKER1 still fires on genuine city-scatter; D1/D2 demonstrate the two defects; D3 documents the Fix-2/replenishment interaction. **Kiro: extend with D1/D2 as failing-then-fixed cases and commit alongside the hardening fix.**

## 6. On the design question: "works must be in Wikidata's listing"

Michael's ruling is correct, with one precision. The pipeline never required the *museum* to be in Wikipedia — venue resolution already treats Wikidata as ground truth for "is this a real place." The problem is the **per-work gate**: every stop had to match a title discovered in Wikidata ∪ official site ∪ Wikipedia. Those sources index a tiny, fame-biased fraction of what hangs in small museums, so the gate structurally discriminates against exactly the venues (obscure, local, non-English) the degradation ladder was built for.

**The principle to adopt (proposed as binding): external listings are EVIDENCE that upgrades confidence, never a REQUIREMENT to generate.** The corroboration ladder already embodies this for story elements (documented / reported / legend); stop selection should use the same philosophy:
- Venue must resolve (Wikidata or equivalent) — keep. This is the anti-fabrication anchor.
- Verified works → full "documented" treatment, grounded facts injected.
- Unverified GPT-proposed works at a resolved venue → generate with hedged narration and an `unverified` flag, at every tier — **including medium**, which today still silently drops unverified candidates and caps the tour at the verified count (a museum with 3 verified + 7 real-but-unlisted works gets a 3-stop tour; same disease, milder symptom).
- Clean-fail remains only for unresolvable venues.

Fix 1 is a correct first step confined to thin tier. The generalization is filed as a design task requiring an approach comment before coding (CIL).

## 7. Bugs found in the same log (routed separately)

1. ~~Russian never requested by the app~~ **RETRACTED (Michael's correction, 2026-07-14).** The app BY DESIGN generates English first (no `language` param on the tour request — all historical logs echo `"language": "en"`, including sessions that produced Russian tours) and requests translation via a separate `TranslationService.translateTour()` call after download (`tour_generator_screen.dart` → `_processAdditionalLanguages`, `tour_translation_helper.dart`). Generation failed, so translation was correctly never attempted. Not a bug; task `wdvrdawkxr` closed with retraction comment.
2. **First TOUR_STATUS poll returns HTTP 404** (both jobs, ~10–20 s after queue), then a later poll succeeds. Endpoint mismatch or job-registration race. → Mobile Kiro triage with Services.
3. **Generic error instead of structured clean-fail** for BLOCKER1/4b paths (see §2.5). → Services Kiro (folded into hardening task).
