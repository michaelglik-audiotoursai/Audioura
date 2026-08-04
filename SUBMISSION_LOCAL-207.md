##### READY FOR REVIEW

**Commit:** a99474e
**Branch:** kiro/local207-secret-scan-gate
**Base:** storied

---

## Summary

`secret_scan.py` — a zero-dependency pre-merge secret scanner with three modes
(`--staged`, `--range A..B`, `--tree`). Exits non-zero on any finding.

### Key fix from bounce #2

The OpenAI and Anthropic detectors now detect the **shape of the secret
anywhere in the line** — no requirement for a preceding quote or `=`. The
historical exposures in this repo were keys pasted bare into prose and markdown
tables. A scanner that requires assignment context misses all of them.

### Files changed

| File | Purpose |
|------|---------|
| `secret_scan.py` | Scanner: 7 detectors, 3 modes, whitelist, near-match |
| `tests/test_secret_scan.py` | 42 tests: each detector, each whitelist case, regression tests for historical exposure forms |
| `SUBMISSION_LOCAL-207.md` | This file |

---

## Evidence: scanner catches the exposures that motivated it

### Bare key in prose (the decisive test from bounce #2)

```
$ python3 -c "from secret_scan import detect_openai; print(len(detect_openai('The key sk-proj-Mv3Rq8Zw1Xn5Yb7Kf2Jt4Ld9Gs0Uc6PeHa3W has hit quota', 1, 'x.md')))"
1
```

### --range on the commit that introduced sk.py (root commit)

```
$ python3 secret_scan.py --range 4affef043f..4affef043f 2>&1 | grep sk.py
  [openai_key] 4affef043f 2025-10-26 sk.py:4   → sk-proj-…[73 chars]
  [near_match_secret] 4affef043f 2025-10-26 sk.py:4   → sk-proj-…[73 chars]
  [openai_key] 4affef043f 2025-10-26 sk.py:7   → sk-proj-…[69 chars]
```

### --range on the AWS key exposure

```
$ python3 secret_scan.py --range 049bb35d9f~1..049bb35d9f 2>&1 | grep aws
  [aws_access_key] 049bb35d9f 2026-06-07 claude_review_secret_fixes_final_2026_06_07.md:25   → AKIAWLW3…[20 chars]
```

### --range on SUBMISSION_LOCAL-162.md (subscribed branch)

```
$ python3 secret_scan.py --range 01421b41fd~1..01421b41fd 2>&1 | grep aws
  [aws_access_key] 01421b41fd 2026-08-03 SUBMISSION_LOCAL-162.md:192   → AKIAWLW3…[20 chars]
```

### --tree mode on current working tree

```
$ python3 secret_scan.py --tree 2>&1 | grep "openai_key\|aws_access_key\|near_match"
  [aws_access_key] claude_review_secret_fixes_final_2026_06_07.md:25 → AKIAWLW3…[20 chars]
  [openai_key] sk.py:4 → sk-proj-…[73 chars]
  [near_match_secret] sk.py:4 → sk-proj-…[73 chars]
  [openai_key] sk.py:7 → sk-proj-…[69 chars]
```

### Tests: 42 passed, 0 failed

```
$ python3 tests/test_secret_scan.py
  ✓ test_cli_staged_mode
  ✓ test_cli_tree_mode
  ✓ test_detect_anthropic_bare_in_prose
  ...
  ✓ test_detect_openai_bare_in_prose
  ✓ test_detect_openai_bare_in_markdown_table
  ✓ test_detect_openai_in_curl_command
  ✓ test_detect_openai_in_error_message
  ...
  Results: 42 passed, 0 failed, 42 total
  All tests passed!
```

---

## Historical audit: files that have ever contained a recoverable secret

| Commit | Date | File | Secret type | Recoverable chars | Still live in `.env`? | Anything imports it? |
|--------|------|------|-------------|-------------------|-----------------------|---------------------|
| 4affef04 | 2025-10-26 | `sk.py` | OpenAI key | 73 (full key) | **YES** — same as `OPENAI_API_KEY` in `.env` | **NO** — nothing imports `sk.py` |
| 049bb35d | 2026-06-07 | `claude_review_secret_fixes_final_2026_06_07.md` | AWS access key | 20 (full key ID) | **YES** — same as `AWS_ACCESS_KEY_ID` in `.env` | N/A (markdown) |
| 01421b41 | 2026-08-03 | `SUBMISSION_LOCAL-162.md` (subscribed only) | AWS access key | 20 (full key ID) | **YES** — same as `AWS_ACCESS_KEY_ID` in `.env` | N/A (markdown) |

### Not a full exposure (corrected from prior submission)

| Commit | Date | File | What's there | Why not actionable |
|--------|------|------|--------------|--------------------|
| 4f25c8d2 | 2026-07-30 | `SUBMISSION_LOCAL-39.md` | `sk-proj-H6SIHfb...` | Only 15 chars — not a usable key |
| Various | Various | `DECISIONS.md`, review files | `sk-proj-…` 8-12 chars | Masked references, not recoverable |

### False positive noted

`migration/data_small_tables.sql:495` — matches `sk-or-ellison-buy-tiktok`
(a URL slug, not a key). Minor; not worth a special-case filter.

---

## Proposed PROCESS wording

For every task file's `## PROCESS` block:

> Never hardcode a credential; read `os.environ[...]` with no literal fallback.

(Already present in LOCAL-207's own process block. Proposing LEAD add it to
the task file template.)

---

## Limitations

1. **AWS secret keys** still require assignment context (variable name hint)
   because a bare 40-char base64 string has too high a false-positive rate.
   The actual AWS secret was never found bare in prose in this repo — only the
   access key ID (AKIA prefix) was.

2. **History purge not performed** — Michael's decision per D79. The keys
   remain in git history.

3. **No key rotation performed** — gated on Michael per D79.

4. **One known false positive class**: URL slugs starting with `sk-` longer
   than 23 chars (e.g. `sk-or-ellison-buy-tiktok`).
