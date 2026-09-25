# SUBMISSION — LOCAL-521: Validate user-chosen stops before generating

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-521-user-stops-validate`
**Base:** storied (`e1341e6`) — verified `git merge-base --is-ancestor e1341e6 HEAD` exits 0.

## What this does

A user can type anything into the stops box. Before a single token is spent
generating, `user_stops_validate.validate_stops()` runs the three judges that
already exist for this — `place_shape.classify_stop_name`, `geo_refutation`, and
`venue_parts.resolve_part_instances` output — over the user's list and returns a
three-valued verdict per stop:

| verdict     | meaning                                            | generates? |
|-------------|----------------------------------------------------|------------|
| `rejected`  | we can **refute** it (format, category, or geography) | no      |
| `warning`   | plausible but **unconfirmed** (venue seems to lack it) | yes    |
| `ok`        | a real, named place with nothing against it           | yes    |

This is Michael's D577 made operational: **we ship what we cannot verify, we do
not ship what we can refute.** The floor is *not refuted*, not *verified*.

## How it maps to the existing modules

- **Shape (`place_shape.classify_stop_name`)** — deterministic string logic. A
  FORMAT ("Audio Guide") or a CATEGORY ("Restaurants in Nice") is refutable from
  the words alone → `rejected`. This is the LOCAL-481 rule applied to user input.
- **Geography (`geo_refutation.refute_stop_by_distance`)** — with an injected
  geocoder, a stop whose own name places it far from the venue is refuted. The
  D564 Sistine Chapel case: "Sistine Chapel Ceiling (Vatican City)" resolves
  6,593.9 km from a Newton MA venue → `rejected`.
- **Venue parts (`venue_parts.resolve_part_instances` output)** — when the caller
  passes the `{part: {count, names, access}}` map, a stop the venue reports
  `count == 0` of is **not** refuted — we could not *confirm* it, so it is a
  `warning` and still generates (D577). "we could not confirm" and "there are
  none" are different answers, but neither is a refutation of the *user's intent*
  to visit it; the listener is told, not overruled.

**Injected edges, deterministic core.** The geocoder and `ask_grounded` are never
called by this module directly — they are passed in, so tests run offline. When an
edge dependency is absent, that check is **skipped, never turned into a rejection**:
an unavailable verifier cannot refute anything.

## Acceptance — all four met (verified by test + live run)

1. **Each stop returns ok/warning/rejected with a readable reason.**
   `TestAcceptance1_*` — every result carries a `verdict` and a non-empty `reason`.
2. **A stop 6,000 km from the venue is rejected (D564).**
   `TestAcceptance2_*::test_sistine_chapel_...` asserts `REJECTED` with `km > 6000`.
3. **A plausible-but-unconfirmed stop is a WARNING and still generates.**
   `TestAcceptance3_*` — a `count == 0` part is `WARNING` and appears in
   `generatable(result)`.
4. **Nothing is dropped silently.**
   `TestAcceptance4_*::test_every_input_appears_exactly_once_in_output` — every
   input stop is returned in order; the `rejected` list names each refused stop
   with its reason for the caller to show the user.

A `TestItCanFail` case (D242) proves the geography check really fires: raising the
threshold to 50,000 km lets the Vatican stop pass — the red state.

## Files

- `user_stops_validate.py` — the validator (new).
- `tests/test_local521_user_stops_validate.py` — 18 tests, all passing (new).

## Verification

```
python3 -m pytest tests/test_local521_user_stops_validate.py -q
# 18 passed

python3 -m pytest tests/test_d577_geo_refutation.py tests/test_local481_place_shape.py -q
# 18 passed  (dependencies still green — nothing broken)
```

Live run over a mixed list (`Bell Tower`, `Audio Guide`, `Restaurants in Nice`,
`Sistine Chapel Ceiling (Vatican City)`, `Crypt`):

```
ok        | Bell Tower           -> names a specific place
rejected  | Audio Guide          -> tour format, not a place
rejected  | Restaurants in Nice  -> category ('restaurants') inside a place — which restaurant?
rejected  | Sistine Chapel Ceiling (Vatican City) -> geocodes to Vatican City, 6593.9 km from the venue
warning   | Crypt                -> venue does not appear to have 'Crypt' — generating anyway, flagged
SUMMARY: 1 ok, 1 warning, 3 rejected
GENERATABLE: ['Bell Tower', 'Crypt']
```

## Integration note (not wired here)

This module is a pure judge with no side effects. A caller (e.g. the orchestrator's
pre-generation step) would call `validate_stops(user_list, anchor=..., geocoder=...,
part_instances=...)`, send `generatable(result)` to generation, and surface the
`rejected`/`warning` reasons to the user. Wiring it into the request path is left
for a follow-up so this change stays reviewable and self-contained.
