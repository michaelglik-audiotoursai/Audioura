# SUBMISSION — LOCAL-798

**Tour-name search was an exact phrase: "Mui Ne seafood*" found nothing even
though tour 466 "Seafood restaurants in Mui Ne, Vietnam - Tour" exists.**

- **Base:** subscribed (`eaade7d2`) — verified `git merge-base --is-ancestor eaade7d2 HEAD` exits 0.
- **Branch:** `LOCAL-798-name-search-tokens`

## Root cause

`/search-tours` matched the WHOLE query as one contiguous substring:

```
tour_name ILIKE '%mui ne seafood%' OR request_string ILIKE '%mui ne seafood%'
```

So the words had to appear adjacent **and in that order**. Tour 466 stores the
words in a different order ("Seafood … Mui Ne"), with "restaurants" and "in"
interleaved, so the phrase never matched. A trailing `*` only turned the final
`%` into an anchor — it did not split the words.

The bug lives in the deployed map-delivery (`map_delivery/app.py`, the image
built by `docker-compose-master` / `docker-compose.subscribed-local`, reached
via the gateway `/search-tours` → `pattern=` from the app) and in the
sibling `map_delivery_service.py` named in the ticket (`?query=`). Both are
fixed; no gateway change.

## Fix (map-delivery only)

A new token layer, shared (same helpers) by both files:

1. **Tokenise** the query: drop a trailing `*`, strip punctuation, fold
   diacritics (NFKD + drop combining marks + lower-case, so "Mũi Né" → "mui ne"),
   split on non-alphanumerics, drop stop-words
   (`a an the of in on at to for and or near by with from tour tours`).
2. **Match**: a tour matches when **every** token appears in `tour_name` **OR**
   `request_string` — AND across words, any order. Case- and diacritic-
   insensitive.
   * When Postgres `unaccent()` exists, the fold is done **in SQL** (precise,
     set-based): `unaccent(LOWER(col)) LIKE unaccent(%s)` per token.
   * When it does not (our GCloud/test/live DBs today), the **ASCII** tokens
     bound a candidate set in SQL and a Python fold (`_token_match_py`) confirms
     the full diacritic-insensitive AND over that bounded set — so the extension
     is never required and the endpoint never 500s.
3. **Rank** (default order of a name search): tours with **all** query words in
   the `tour_name` first, then those with **more** words in the name, then the
   **newest** (`created_at`), then popularity. A name search is global, so
   distance is **not** a sort key here (it stays in the payload for the client).
   Explicit `?sort=match` and `?sort=top_rated` are untouched.
4. A **single-word** query (and the LOCAL-680 `*` wildcard contract) keeps the
   exact historic single-`ILIKE` behaviour — the token layer engages only for
   multi-word queries, so nothing else about search changes.

**Preserved exactly:** the `track` filter (LOCAL-737/770), the content-rating
gate (LOCAL-687), the community members-only visibility gate (LOCAL-701/753),
the Free/Paid and min-rating filters, translation handling, and the full
response shape (the internal `_rank_*` keys are stripped before `jsonify`).

## Files changed

| File | Change |
|------|--------|
| `map_delivery/app.py` | Token helpers + token-AND WHERE, Python-fold fallback, LOCAL-798 ranking in `/search-tours`. Added `import re` (the module lacked it). |
| `map_delivery_service.py` | Same token helpers + token-AND WHERE (audio_tours **and** custom_tours) + ranking in `/search-tours`; `created_at` added to the audio_tours SELECT for the "newest" tiebreak. |
| `tests/test_local798_name_search_tokens.py` | New tests (below). |

## Tests

`tests/test_local798_name_search_tokens.py` — **9 passed**:

- **PureHelperTest** (no DB, always runs) — the tokeniser + matcher lifted from
  **both** service files: trailing-`*`/punctuation/stop-word stripping, diacritic
  fold, word-order independence; the four queries match tour 466's text;
  "Mui Ne pizza" does not; word-in-name ranking counts correctly.
- **DeployedSearchRouteTest** — the real `map_delivery/app.py` `/search-tours`
  route over a hermetic scripted cursor with `unaccent()` forced OFF (the live
  path): the four queries return tour 466 with the **response shape intact** and
  no `_rank_*` leak; "Mui Ne pizza" returns zero; an all-words-in-name tour ranks
  ahead of a more-popular request-string-only hit.
- **RealDbSearchSqlTest** — drives `map_delivery_service.py` `/search-tours`
  against a **throwaway Postgres schema** (`tests/_isolated_db.py`) seeded with 3
  tours, so the **actual SQL WHERE** is exercised: the four queries find tour
  466; "Mui Ne pizza" does not; the response shape is unchanged; the `track`
  filter still isolates subscribed vs beta. Teardown DROPs the schema and asserts
  `public` row counts are identical before/after (no production write; no DELETE).

### Full suite vs baseline

Ran every test that touches map-delivery (28 files) on the clean base (my two
code files stashed) and on the branch, diffing the failure sets:

- Baseline: 23 failed + 1 collection error (a non-test in-container proof script),
  27 unique failing IDs.
- Branch: **the same 27 failing IDs — ZERO new failures — and +9 new passing**
  (this ticket's tests; 278 → 287 passed).

The pre-existing failures are unrelated `get_tour_by_code` / `tour-info`
column-count issues (local666/671/672 …) that fail identically on `eaade7d2`.

## Live test (own containers, `-p local798`, cap $0)

Brought up throwaway containers under compose project **`local798`**:
`postgres:14-alpine` (md5 auth, so the image's old libpq connects) seeded with 3
tours — tour **466** "Seafood restaurants in Mui Ne, Vietnam - Tour"
(`track=subscribed`) + two beta decoys (Pizza Rome, Street food Hanoi) — and the
**built `./map_delivery` image** on host port 5799.

HTTP `GET /search-tours?pattern=…`:

| Query | Result |
|-------|--------|
| `Mui Ne seafood` | **466** ✅ (the reported bug) |
| `seafood mui ne` (reordered) | **466** ✅ |
| `MŨI NÉ Seafood*` (diacritics + `*`) | **466** ✅ |
| `seafood` (single word) | **466** ✅ |
| `Mui Ne pizza` (negative) | **count 0** ✅ |

Service logs show `unaccent() available: False`, so the **Python-fold fallback**
path handled the "MŨI NÉ" diacritics without the extension. The response carried
the full shape (`rating_distribution`, `price_label`, `match_reason`, `version`,
…) with no `_rank_*` keys. `/search-tours` makes **no external/paid API calls**
→ cap **$0**. Containers, volumes, the built image and the temp dir were torn
down afterward; the live DB was never touched.
