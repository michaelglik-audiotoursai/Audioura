# LOCAL-906G — cross-stop object identity, reduplicated names ($0, offline)

Base 6898556b (906F). Changes in `leftovers_906f.py`:
- `resolve_cross_stop`: two stops link only via `_link_token`: a shared DISTINCTIVE title token (not `_OBJECT_NOUNS`, not generic venue/place words), the same non-scope placeholder (`<Statue>`), or one sentence naming the other stop's distinctive title token. `len(obj&obj)>=2` fallback now only applies after a link exists. Linking token is logged ("linked by 'statue'").
- `_DUP_WORD` only collapses when the repeated word is a generic head; Walla Walla / Bora Bora / Pago Pago / Sing Sing unchanged; Mount Mount, `<Mountain> Mount`, Nui Ba Mount still fixed.
- C: ship/vessel/boat/nation/country in sentence, earlier text or title is a referent for her/she; added mayor/president/premier/chancellor/senator/captain/colonel/admiral to `_ROLES`.
Tests: `tests/test_local906g_cross_stop_identity.py` (both probes, two museums, two statues, 551 shape + log, dup names, ship, Mayor). 906F replays green.
Suite: requested set passes; only pre-existing failures (378 case_sensitive x2, 666, spine real_generation) plus `test_local893…slow_pin_phase` which failed once under load and passes on repeat and in isolation (timing flake).
