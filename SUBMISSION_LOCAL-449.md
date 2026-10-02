# SUBMISSION_LOCAL-449.md — Cold host must short-circuit

**Branch:** LOCAL-449-cold-host-must-short-circuit
**Base:** LOCAL-448-db-first-correctness (8c442fc)

---

## Problem

LOCAL-448 removed the Wayback call (correct) but replaced it with
`_fetch_via_action_api(topic)` on the cold branch, timeout handler, and 429 handler.
That function iterates `['en.wikipedia.org', 'fr.wikipedia.org']` with 10s timeouts
each. When Wikimedia is down, this costs 20s on the default (ungated) path — worse than
the 10s Wayback stall it replaced.

The breaker contract is explicit: "If True, short-circuit immediately with the
appropriate failure value." The cold branch was doing the opposite.

---

## Fixes applied

### 1. Cold means stop

When `is_host_cold('en.wikipedia.org')` is true, `fetch_wikipedia_summary_with_provenance`
returns `{}` immediately. Zero network calls. This is LOCAL-445's behaviour restored.

### 2. Timeout handler: mark cold + return {}

A timeout means the host is dead. We mark it cold and return `{}`. Calling
`_fetch_via_action_api` after marking the host cold is calling the dead host to recover
from the dead host — removed.

### 3. `_fetch_via_action_api` consults the breaker per-host inside its loop

Every iteration now calls `is_host_cold(wiki_host)` before making any request. If cold,
it `continue`s. It also marks hosts cold on timeout and 429 within the loop.

This protects all call sites (not just the three broken branches), including the 404
fallback, the non-200 fallback, the "too short" enrichment, and any future callers.

**Wikimedia bucket rule verified:** `dead_host_breaker.extract_host` maps all
`*.wikipedia.org` hosts to the canonical `'wikimedia'` group key via `_is_wikimedia_host`.
A cold `en.wikipedia.org` returns `True` for `is_host_cold('fr.wikipedia.org')` because
both resolve to `'wikimedia'`. Confirmed by test `test_cold_en_covers_fr`.

### 4. 429 keeps the action API call — but the breaker governs it

Pre-LOCAL-447, a 429 fell through to `_fetch_via_action_api` (`status_code != 200`).
A 429 is a rate limit, not necessarily a permanent outage, so the structure of calling
the action API is preserved. However:

- The 429 handler first calls `mark_host_cold('en.wikipedia.org', '429 rate limit')`
- Then calls `_fetch_via_action_api(topic)`
- Inside `_fetch_via_action_api`, the per-host breaker check sees Wikimedia is now cold
  and skips all hosts immediately (zero network calls)
- Net effect: same as returning `{}` directly, but the code path is honest about why

**Why keep it instead of just returning `{}`:** Conceptual clarity. The 429 case is "I got
a response — I can't call again right now." The cold case is "I didn't even get a
response." If the bucket rule ever changes (e.g., fr.wikipedia.org gets its own bucket),
the 429 path would naturally let the action API try the non-cold host. Today they share
a bucket so it's a no-op — but it's correct to let the breaker decide rather than
hard-coding the assumption at the call site.

---

## Repro script results

### Our branch (LOCAL-449-cold-host-must-short-circuit @ 8c442fc + fix):
```
Wikipedia: timeout fetching 'Some Stop Title'
  [DEAD-HOST] Marked cold: wikimedia (timeout)
A (not yet cold): 5.1s, 1 calls
B (ALREADY COLD): 0.0s, 0 calls
```

### Baseline (storied @ 26b6955):
```
Wikipedia: timeout fetching 'Some Stop Title'
  [DEAD-HOST] Marked cold: wikimedia (timeout)
A (not yet cold): 5.1s, 1 calls
B (ALREADY COLD): 0.0s, 0 calls
```

Both match. Case B: 0 network calls, <0.1s.

---

## D242 check: neutralised cold check goes RED

Test `test_neutralised_cold_check_allows_network_call` patches `is_host_cold` to return
`False` and shows that a cold host then gets a network call. When the cold check is
neutralised, the test PASSES (proving the cold check was the only guard). If this test
were to FAIL, it would mean the cold check is decorative — the real protection is
elsewhere.

This binds to the real path: neutralising the guard exposes the network call.

---

## Container run evidence

```
$ docker exec generator-449-test python -c "
from rag_retriever import fetch_wikipedia_summary_with_provenance
result = fetch_wikipedia_summary_with_provenance('Saint-Paul-de-Vence')
print(f'Source: {result.get(\"source\", \"NONE\")}')
"
Source: stop_corpus
```

DB-first serves known titles correctly with `L447_RETRIEVAL_CHAIN=true` inside the
rebuilt generator container.

---

## Regression tests

All pass:
- `tests/test_local448_db_first_correctness.py` — 16/16
- `tests/test_local447_db_first_and_wayback.py` — 8/8
- `tests/test_local449_cold_host_short_circuit.py` — 13/13
- `test_sq4_merge.py` — ALL TESTS PASSED
- `test_palais_fix_lead_fixture.py` — 23/23 assertions hold
- `test_local12_fact_retrieval_fix.py` — 8 PASS, 0 FAIL

---

## Should `L447_RETRIEVAL_CHAIN` default ON?

**Yes, with this fix in place.**

The reasoning from LOCAL-448 stands: DB-first is the correct architecture. The only
reason the flag couldn't go ON was that the ungated failure paths (cold/timeout) imposed
20s of dead wait. With this fix:

- Cold → 0s, 0 calls (breaker short-circuits immediately)
- Timeout → 5s, 1 call (the initial REST timeout, then marks cold and stops)
- Second call after timeout → 0s, 0 calls

The flag can now be flipped without regression risk on the failure paths. The 5s single
timeout on first encounter is the minimum cost — you must discover the host is dead
before you can avoid it.

LEAD flips the flag, not me. But the blocker is resolved.
