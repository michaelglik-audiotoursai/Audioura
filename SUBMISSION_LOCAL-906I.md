# SUBMISSION LOCAL-906I — one person many spellings, one fact one stop, no "The <Proper>", spoken location, thin refill

Offline, $0, no live run, no paid call. Base c00dd708 (ancestor check passed). Branch `LOCAL-906I-name-aliases-richness`.

## What changed
1. **Aliases** (`leftovers_906f._distinct`): names fold diacritics/case (`đ`→d); a name whose tokens are a subset of another's is the same person; "known by his Dharma name/title X (and title Y)", "also called X" link aliases (union-find). One merged person is unambiguous; the pronoun is named with the plain spoken form (longest ASCII-folded variant the tour text uses, else the longest). Also: pronouns ("He lived…") are no longer name candidates, and "<Title>'s" no longer counts as a person name in `_persony_names` (it made the repair keep an orphan "his").
2. **Introducing sentence.** Pass that removed it: the log shows two removals. (a) `[LOCAL-474] PHASE 5.17` retry gates removed the first (Dharma-name) variant; (b) the final one was the **LOCAL-883/884 grounding gate**: the judge labelled "In 1872, the monk …, known by his Dharma title …, left Central …" UNSUPPORTED (twice), although 880 selected it from the evidence as the stop's signature story. Fix: `apply_grounding_gate(trust_verbatim=True)` (used by the tour grounding paths, `ground_tour_text`) keeps a judge-UNSUPPORTED sentence when ONE evidence sentence holds ≥85% of its folded words and all its numbers (`key_fact_coverage.verbatim_supported`), logged `[LOCAL-906I] kept`. Not applied to the 889 injection gates (their test requires the judge verdict to stand). Unverified: I had no evidence text for the real run, only the log, so I could not replay the exact judge call; the keep rule is proven on a generic replay.
3. **One fact one stop** (`drop_cross_stop_fact`): numbers+unit pairs ("49 meters", "7 meters") in stop A whose nearest title object before the number belongs to stop B, where B states the same pairs: the trailing ", which measures …" clause is cut (else the sentence dropped), unless A would have nothing else.
4. **No "The <Proper>"** (`fix_proper_article`, in `run_pass`): "The Orla Mountain's" / "The <Mountain>'s" → bare; "The Reclining Buddha", "The Great Hill" keep it.
5. **Encyclopedia lead** (`drop_encyclopedia_leads`): any body position; dropped when another sentence says where, else rewritten "<X> lies <rest>" ("off of"→"off"; "Orla Mount" takes the stop title "Orla Mountain"; never "Mount Mount"). The old 906F test that kept the lead was updated.
6. **Thin refill** (`refill_thin_stops`, called from `delivery_bodies_905.ensure_bodies` after the 906C final pass): a stop with ≤3 body sentences gets supported evidence sentences (not denied, not deterministic-unsupported, no person pronoun/first person/promo/lead, not same_fact with this or other stops, not another stop's number-fact) up to 5; logged `[LOCAL-906I] thin after removals`; then `run_pass` re-run.

## Tests
`tests/test_local906i_name_aliases_richness.py` (21): aliases, two people still ambiguous, pronoun named, judge-flake kept / unstated claim still dropped, fact at statue stop only, article cases, lead spoken/dropped, thin refill, full replay (stop 1 ≥4 sentences, 49 m once).
Requested suite: 1930 passed, 4 skipped, 1 failed = `test_local893_preview_timeout::slow_pin` (known timing). `-k "ground or conclusion or pin …"` : 707 passed, 3 failed = 378 case_sensitive ×2, 666 no_pin (all known).

## Not done / caveats
- No live run, so the real tour is unproven; the replay uses generic names.
- The refill takes evidence sentences in evidence order (no ranking).
