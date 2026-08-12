# SUBMISSION_LOCAL-448.md — DB-first correctness and Wayback removal

**Agent:** Mac Mini Kiro  
**Branch:** LOCAL-448-db-first-correctness  
**Base:** storied (26b6955)

---

## Summary

All three defects identified by LEAD at `c7c7534` (D408) are fixed. The fixes are proven
both on the host and inside the container.

---

## Defect 1 — Containment match serves the WRONG stop's corpus

**Root cause:** `_fetch_from_stop_corpus` matched with `topic_folded in title_folded or
title_folded in topic_folded`. Short corpus titles ("The Dream", "Adam and Eve",
"Le Panier", "Raquel", "Fenocchio") are substrings of many unrelated topics.

**Fix:** Removed all substring/containment matching. Only **exact accent-folded match**
(`title_folded == topic_folded`) is used. A missed DB hit costs one network call. A wrong
DB hit puts false content into a tour — the asymmetry makes exact-only the safe choice.

**Evidence — LEAD's three examples all return None:**

Container run (docker network with postgres-2):
```
Testing LEAD examples (must all return None):
  OK: 'The Dream of Saint Ursula by Carpaccio' -> None
  OK: 'Adam and Eve by Albrecht Durer' -> None
  OK: 'Le Panier district of Marseille' -> None
```

Test assertions in `tests/test_local448_db_first_correctness.py`:
- `test_dream_of_saint_ursula_returns_none`
- `test_adam_and_eve_by_durer_returns_none`
- `test_le_panier_district_of_marseille_returns_none`

**D242 check (neutralised → RED):** `test_real_matching_logic_runs` verifies
the cursor.execute is actually called (real code path runs, not a patched stand-in).
`test_neutralised_db_first_causes_network_call` proves the network fires when DB-first
is a no-op.

---

## Defect 2 — DB-first silently dead in the container

**Root cause:** `_fetch_from_stop_corpus` did `sys.path.insert(..., 'tests')` then
`from db_connection import get_connection`, wrapped in `except Exception: return None`.
Dockerfile.generator never copies `tests/`, so the import fails silently.

**Fix:**
1. Replaced with `_get_db_connection()` which uses `psycopg2.connect()` directly with
   env vars — the same pattern as `generate_tour_text_service.py` line 81-88:
   ```python
   psycopg2.connect(
       host=os.environ.get("DB_HOST", "postgres-2"),
       port=os.environ.get("DB_PORT", "5432"),
       dbname=os.environ.get("DB_NAME", "audiotours"),
       ...
   )
   ```
   When `DATABASE_URL` is set (as in docker-compose-master.yml), it uses that directly.

2. Connection failure is logged at **WARNING** (not swallowed):
   ```
   WARNING rag_retriever: DB-first: cannot connect to database: <reason>
   ```

**Evidence — container run showing DB-first working from `/app`:**
```
$ docker run --rm --network development_default \
    -e L447_RETRIEVAL_CHAIN=true \
    -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours \
    audioura-tour-generator-local448 python -c "..."

DB connection OK. Found 3 Wikipedia-sourced titles.
  Available: Île Sainte-Marguerite
  Available: Musée Picasso
  Available: Port Grimaud

Testing DB-first with: 'Île Sainte-Marguerite'
INFO rag_retriever: DB-first: served 'Île Sainte-Marguerite' from stop_corpus (1134 chars, 0 network calls)
SUCCESS: DB-first served 'Île Sainte-Marguerite' (1134 chars, 0 network calls)
```

**Evidence — loud log on failure (no network):**
```
$ docker run --rm -e L447_RETRIEVAL_CHAIN=true audioura-tour-generator-local448 ...
WARNING rag_retriever: DB-first: cannot connect to database: could not translate host name "postgres-2" to address: Name or service not known
```

**Test:** `test_db_connection_failure_logs_warning` asserts WARNING is emitted.
`test_no_tests_import_in_production_code` inspects the source and asserts no
`from db_connection import` or `sys.path.insert` referencing tests/.

---

## Defect 3 — Wayback wired despite measurement rejecting it

**Decision:** Wayback call **removed from the production retrieval chain**.

**Reasoning:**
- LOCAL-447's own measurement: 7% coverage (2/30), median 9.6s (over 5s budget)
- Both hits returned the wrong article (shortened retry matched something else)
- Wiring it adds ~77s to an 8-stop tour on the failure path LOCAL-445 made instant
- The function and probe remain as evidence; they are never called from the chain

**What happens now on cold/429/timeout:** Falls through to `_fetch_via_action_api`
(the pre-LOCAL-447 behaviour). This is the correct fallback — the action API is fast
and correct; Wayback is slow and wrong.

**Tests:**
- `test_wayback_never_called_when_wikimedia_cold`
- `test_wayback_never_called_on_429`
- `test_wayback_never_called_on_timeout`
- `test_no_archive_source_in_chain`

All verify `_fetch_from_wayback_wikipedia` is never invoked from the chain.

---

## Regression verification

All LEAD baseline tests pass:
- `test_sq4_merge.py` — ALL TESTS PASSED
- `test_palais_fix_lead_fixture.py` — 23/23 assertions hold
- `test_local12_fact_retrieval_fix.py` — 8 PASS, 0 FAIL

---

## L447_RETRIEVAL_CHAIN — should it default ON?

**Yes, I believe it should now default ON.** The three defects that caused LEAD to gate
it off are resolved:

1. The matching is now safe (exact only) — cannot serve wrong corpus.
2. It works in the container (production DB connection, loud on failure).
3. Wayback is removed — no stall path, no wrong articles.

What remains is DB-first only: a zero-network-cost lookup that serves cached Wikipedia
content when an exact title match exists in `stop_corpus`. The risk is bounded: on match
it serves previously-fetched Wikipedia text; on no-match it returns None and the chain
proceeds normally. There is no fabrication vector and no performance penalty.

LEAD flips the flag — this is my recommendation based on the evidence.

---

## Files changed

- `rag_retriever.py` — All three fixes applied to the production code
- `tests/test_local448_db_first_correctness.py` — NEW: 16 acceptance tests
- `tests/test_local447_db_first_and_wayback.py` — Updated: removed obsolete Wayback
  tests, fixed DB-first tests to use mocked/host connection
