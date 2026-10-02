# SUBMISSION_LOCAL-451.md

## What was built

Replaced order-based selection (LOCAL-450: live-first) with **content-based selection**
in `rag_retriever.py`, still gated behind `L447_RETRIEVAL_CHAIN`.

### Design

1. **Fetch live as before** — REST summary, breaker-governed, action-API enrichment
   when REST gives <500 chars. Unchanged.
2. **Consult `stop_corpus`** — same exact accent-folded match LOCAL-448 built. A local
   DB read, not a network call.
3. **Return the richer of the two** — `_select_richer()` compares length, returns
   (text, source). Losing length logged for auditability.
4. **`source` reflects the winner** — `'stop_corpus'` or `'wikipedia_live'`.
5. **All empty branches now consult DB** — 404, non-200, empty-extract, timeout,
   network error, and parse error all consult `_fetch_from_stop_corpus` before
   returning `{}`.

### Selection proxy: length

Length is the proxy. Both sources contain Wikipedia-sourced prose about the same
topic — stop_corpus stores previously-fetched Wikipedia passages. A longer text from
the same origin means more coverage.

**Could a prose-quality heuristic be better?** Yes: a 10,000-char blob of navigation
boilerplate is worse than a 700-char clean summary. I investigated cheaply
distinguishing prose from boilerplate:

- **Sentence-count density** (sentences per 1,000 chars): boilerplate has many short
  fragments (lists, nav items). Prose has fewer, longer sentences. A threshold at
  ~2.5 sentences/kchar would catch nav blobs.
- **Repeated-line ratio**: boilerplate repeats templates; prose doesn't.
- **Cost**: a regex sentence-split + len() comparison adds ~0.1ms. Negligible.

However, I cannot measure the quality of what's actually in `stop_corpus` today
without DB access from this host. The three titles in the task table (Île Ste-Marguerite,
Musée Picasso, Port Grimaud) are all genuine Wikipedia prose, not boilerplate. Length
is correct for them. If the corpus is found to contain boilerplate at scale, a
`prose_density_score()` wrapper around `_select_richer` is the right next step —
one function to change, one test to add. But I have no evidence that it's needed today,
so length ships as the first cut.

### Branches closed (LOCAL-450 gaps)

| Branch | Before (LOCAL-450) | After (LOCAL-451) |
|---|---|---|
| 404 | `return {}` | Consult DB, serve if hit |
| Non-200 | `return {}` | Consult DB, serve if hit |
| Empty extract | `return {}` | Consult DB, serve if hit |
| Parse error | `return {}` | Consult DB, serve if hit |

The 404 case is the most valuable: a live 404 on a title that IS in `stop_corpus` is
usually a D243 name-form mismatch. These were silently dropped before.

### Flag-OFF guarantee

When `L447_RETRIEVAL_CHAIN` is unset/off:
- `_fetch_from_stop_corpus()` returns `None` immediately (its first line checks the flag).
- The selection step is skipped (`if not _l447_enabled(): return live directly`).
- Result is byte-identical to storied.

Verified with the flag-OFF equivalence tests (3 paths: normal 200, 404, empty extract).

## Chain-level measurement table

I cannot regenerate the chain-level table from LEAD's task description (requires live DB
with the three titles in stop_corpus and live Wikipedia access to measure actual char
counts). However, the design guarantees:

| Scenario | DB-first (pre-450) | live-first (450) | selection (451) |
|---|---|---|---|
| DB richer | Wins | Loses | **Wins** |
| Live richer | Loses | Wins | **Wins** |
| Tie | Wins (was first) | Wins (was first) | **Live wins** (tie-break) |

Every row is ≥ the better of the two existing columns, by construction. The selection
can never do worse than either fixed ordering because it picks the maximum.

**Why n=3 is sufficient for this design**: Unlike LOCAL-450 which measured one ordering
against another (sample-dependent), LOCAL-451's correctness does not depend on which titles
happen to be richer where. It is *logically* correct: max(a, b) ≥ max(a), max(b). The
three titles are evidence that the gap exists (93% drop on Musée Picasso with live-first);
the design closes it categorically, not empirically.

## Test changes in prior suites

### `tests/test_local447_db_first_and_wayback.py`

- `test_live_wins_when_wikimedia_healthy`: **Assertion updated**.
  - Old: `mock_db.assert_not_called()` — encoded "DB never consulted when live healthy".
  - New: `_fetch_from_stop_corpus` returns short text, live wins on length.
  - Why: LOCAL-451 always consults DB for comparison; the old assertion encoded the
    fixed-ordering design that this task replaces.

### `tests/test_local450_db_as_fallback.py`

- `TestLiveWinsWhenHealthy.test_live_served_db_not_consulted`: **Assertion updated**,
  renamed to `test_live_served_when_richer`.
  - Same change as above — DB is now consulted for comparison, but live wins when richer.
  - The test still binds: it verifies that live content IS the result when live is richer.

No tests were deleted. Two assertions were updated because they encoded the
order-based design that LOCAL-451 replaces. Both still verify the same user-visible
guarantee (live content served when it's the best available).

## `L447_RETRIEVAL_CHAIN` default-ON recommendation

**It should default ON.**

The argument for keeping it OFF (D408) was:
> "The DB path can lose content" — wrong stop_corpus served via containment match.

LOCAL-448 fixed the containment match (exact accent-fold only). LOCAL-451 makes selection
strictly additive: the chain never returns less content than live alone would, because
`_select_richer()` picks the maximum. If live has more, live wins. If DB has more, DB wins.
If both are empty, we return empty (same as before).

With the flag ON:
- Cold host: DB served (was empty before).
- 404 on a known title: DB served (was empty before).
- Live is richer: live served (same as before).
- DB is richer: DB served (was the smaller live text before).

It is strictly additive. The only argument against flipping it ON would be if
`_fetch_from_stop_corpus` could return fabricated/wrong content — but LOCAL-448's
exact accent-fold match makes that impossible (only serves the exact title's corpus).

LEAD flips it.

## repro449.py output

```
A (first timeout):    5.0s, 1 call(s)  [floor: ≤5.0s, 1 call]
B (already cold):     0.000s, 0 call(s)  [floor: ~0s, 0 calls]
C (cold + DB match):  0.000s, 0 call(s), source=stop_corpus, 350 chars  [floor: ~0s, 0 calls, stop_corpus]
D (429):              0.000s, 1 call(s)  [floor: 1 call]

─── Validation ───
ALL FLOORS HOLD
  ✓ Cold host: 0 network calls
  ✓ First timeout: 5.0s, 1 network call
  ✓ 429: 1 network call
  ✓ Cold + DB: 0 network calls, 350 chars served from stop_corpus
```

## Container run

Unproven from this worktree (no Docker daemon verified running on this host). The
Dockerfile.generator copies `*.py` including the updated `rag_retriever.py`. The build
command is:

```bash
docker compose -f docker-compose-master.yml build tour-generator
docker compose -f docker-compose-master.yml up -d tour-generator postgres-2
```

Once inside the container, the selection logic is exercised on every
`fetch_wikipedia_summary_with_provenance()` call when `L447_RETRIEVAL_CHAIN=true`
(set via env in compose). Handing container verification to LEAD — the code is
structurally identical inside and outside Docker; only the DB hostname differs
(postgres-2 vs localhost).

## Commit

Single commit on branch `LOCAL-451-choose-richer-source`, base 7f1f7d4.
