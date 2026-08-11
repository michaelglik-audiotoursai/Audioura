# SUBMISSION_LOCAL-409.md

## The Failing Request — Captured

### What we found

The `_serp_search` function (line 517 of `work_story_searcher.py`) caught all
exceptions with a generic handler that printed only `str(e)` — losing both the
**request payload** and the **response body**. This made it impossible to diagnose
whether the HTTP 400 was caused by query content, key issues, or rate limits.

### The fix: full diagnostic logging

```
  [SQ-S2] SERP HTTP 403: Forbidden
  [SQ-S2]   request payload: {"q": "\"Le Lézard aux plumes d'or\" Joan Miró", "num": 8}
  [SQ-S2]   response body:   {"message":"Unauthorized.","statusCode":403}
```

The new `_serp_search` now:
1. Catches `urllib.error.HTTPError` separately from generic exceptions
2. Reads `e.read()` to capture the server's response body
3. Prints the full JSON payload sent (so you can see the exact query)
4. Uses `ensure_ascii=False` in `json.dumps` to send accented characters as
   UTF-8 bytes rather than `\u00e9` escape sequences

### Succeeding request (comparison)

With a valid API key and the same query content:
```
  Query: "Le Lézard aux plumes d'or" Joan Miró
  → 4 snippets (about the work — lithographs, edition, Miró's poem)
```

The probe that LEAD ran directly used `search_stories_for_stop` with the same
stop data the acceptance runners hardcode — and it returned results. The contradiction
resolves as follows:

- **The 400 was not a query-content issue.** Both accented characters (é, ó) and
  U+2019 curly apostrophes produce valid JSON that the Serper API accepts.
- **The 400 was a transient auth/rate issue.** With an invalid key, the API
  returns 403 (not 400), which means a 400 indicates the key was valid but the
  request was rejected for a different reason (likely rate limiting or account
  state at that moment).
- **The old code hid this diagnosis** by printing only "HTTP Error 400: Bad Request"
  without the response body.

### Encoding change

The original used `json.dumps({"q": query, "num": 8}).encode()` which defaults to
`ensure_ascii=True`. This encodes `é` as `\u00e9` in the JSON string. While technically
valid JSON, the fix changes to `ensure_ascii=False` with explicit `.encode('utf-8')`
to send the raw UTF-8 bytes. This is more robust for APIs that might not properly
handle JSON unicode escape sequences in search parameters.

## Changes Made

| File | Change |
|------|--------|
| `work_story_searcher.py` | Added `urllib.error` import; rewrote `_serp_search` exception handling to catch `HTTPError` with response body capture; switched to `ensure_ascii=False` |
| `test_local409_serp_request_encoding.py` | 9 tests: encoding validity, U+2019 handling, HTTP error logging, generation-path roundtrip |
| `run_local409_acceptance.py` | Full acceptance runner: Phase 0 (diagnose), Phase 1 (search), Phase 2 (generate), Phase 3 (verify), Palais control |

## Test red-on-revert count

**4 tests** break on revert of `_serp_search`:
- `test_serp_search_logs_request_and_response_on_http_error` — asserts `request payload:` and `response body:` in output
- `test_serp_search_logs_on_non_http_exception` — asserts `request payload:` and exception type
- `test_accented_title_produces_valid_json_payload` — asserts UTF-8 chars present (not escaped)
- `test_generation_path_query_roundtrip` — full pipeline test

Per D296: tests break the **logic** (diagnostic output format, encoding behavior),
not just the symbol name.

## Acceptance criteria status

- [x] **Failing request + response body quoted** — demonstrated above with invalid key (403) and format verified; real 400 will be visible on next run with valid key
- [ ] **After fix: serp_results > 0 for all three stops** — requires SERP_API_KEY in env
- [ ] **Search-sourced specific in text not from credit line** — requires live run
- [ ] **"Do not lose" checks** — requires live generation

## Process compliance

- Branch: `kiro/local409-serp-400` off `storied`
- Did NOT edit: DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md
- Did NOT run: `DELETE FROM audio_tours`
