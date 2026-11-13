# SUBMISSION LOCAL-906N — cloud 551 nits (offline, $0)

Base b1b8c205 (LOCAL-906M-anchor-evidence); branch LOCAL-906N-cloud-551-nits. No live run, no paid call.

1. **"here the market, you can see …"** — source: `refill_quality_906k._mode_fix`. "as you walk around" was rewritten to "here",
   leaving "here the market". Now: "As you walk around the market, …" -> "Around the market, …"; "As you walk here, …" -> "Here, …";
   "as you walk here the market" -> "around the market"; "walk around" -> "look around"; any rewrite landing at a sentence start is
   capitalised. Tested at sentence start, mid-sentence and before a comma.
2. **Tri / Y** — `nits_906n.unify_builder_names` (runs in `leftovers_906f.run_pass` before `resolve_cross_stop`, which would otherwise
   treat the pair as a conflict and drop a sentence). Two person names sharing all but the last token, about the same object (same
   linked title or same object noun) -> the spelling the evidence states, article first; ties -> earlier stop. Its own name regex
   accepts a one-letter last token ("Truong Dinh Y"; 906F's `_N` needs 2+ chars and read it as "Truong Dinh"). Logs
   `[LOCAL-906N] builder name unified: '<A>' -> '<B>'`. Different builders and different objects are not merged; if the evidence
   states neither spelling nothing changes.
3. **"ta Cu Mountain"** — delivery guard `nits_906n.restore_proper_case` (end of `leftovers_906f.run_pass`): a multi-word name
   capitalised mid-sentence elsewhere (or in a stop title) regains its capitals; an all-lowercase two-word phrase ("old town") is left.
   Sources fixed: I could not reproduce it from the 906I `strip_proper_article` / 906J repair (both keep "Ta"). Two real lowercasers of a
   sentence-initial proper name were found and fixed: `spoken_text_hygiene.disclose_or_drop_folklore` ("A story told … holds that " + lowered
   first letter) now lowers only after a common opener; `about_museum_stop._lower_lead` keeps a multi-word name. Not confirmed which one
   produced the 551 text (no access to that tour); the guard covers any source.

Tests: `tests/test_local906n_nits.py` (18). Requested suite: 2435 passed, 4 skipped; failures identical to the pre-change baseline (none).
