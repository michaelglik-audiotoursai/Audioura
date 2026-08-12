# SUBMISSION_LOCAL-447.md — Wayback as Wikipedia Substitute: Measured, Then Wired

**Branch:** LOCAL-447-wayback-wikipedia-chain  
**Base:** storied (0258a8a)  
**Date:** 2026-08-12

---

## Part 1 — MEASUREMENT: Wayback Does Not Usefully Substitute for Wikipedia

### Method

`wayback_wikipedia_probe.py` drew 30 real titles from `stop_corpus` (259 rows total;
11 with accents), accent-folded per D243, and measured four axes against live Wayback
Machine responses.

### Results

| Metric | Value | Verdict |
|--------|-------|---------|
| **Coverage: Wayback /wiki/ page** | 2/30 (7%) | ✗ Fatal |
| **Coverage: Wayback REST API URL** | 0/30 (0%) | ✗ Confirmed: API URLs are not archived |
| **Coverage: Live Wikipedia REST** | 14/30 (47%) | Baseline |
| **Freshness: Median snapshot age** | 3,442 days (~9.4 years) | ✗ Stale beyond any reasonable bound |
| **Freshness: Snapshots < 90 days** | 0/2 | — |
| **Freshness: Snapshots < 365 days** | 0/2 | — |
| **Latency: Wikipedia median** | 0.13s | — |
| **Latency: Wayback median** | 9.58s | ✗ 72x slower, exceeds 5s timeout budget |
| **Latency: Wayback exceeding 5s** | 2/2 (100%) | — |
| **Content: Same** | 2/2 (100%) | Misleading — see below |

### Critical Finding: The 2 "Hits" Were Wrong Articles

The two Wayback successes matched *wrong* Wikipedia articles:

1. **"Le Village de grand-mère"** (a painting at MAMAC Nice) → Wayback returned Montreal's Gay Village article. The shortened retry `"Le Village"` hit Wikipedia's disambiguation, and Wayback served an archived version of a completely unrelated page.

2. **"Tempête à Nice"** (a Matisse painting) → Wayback returned Tempête FC (Haitian football club). Same mechanism: the shortened `"Tempête"` matched a different article.

The "100% same" content verdict is an artefact of both sources returning the *same wrong article*. For the actual subjects (the painting, the Matisse work), Wayback provided zero useful content.

### Why It Fails

The task spec's hypothesis was correct: **Wayback archives page URLs, not API query results.** The REST summary endpoint (`/api/rest_v1/page/summary/X`) has 0% coverage. The article page (`/wiki/X`) has 7% coverage for our corpus, but the archived pages are 9+ years stale and the latency (median 9.58s) exceeds the rag_retriever timeout budget (5s REST, 10s action API).

The fundamental issue: our `stop_corpus` titles are artwork names, room names, local landmarks — not major Wikipedia article titles. Wayback cannot help with "Kannon, le bodhisattva de la compassion" or "Guitar by Antonio de Torres (Almeria, 1884)" because Wikipedia never had standalone articles for these subjects.

### Verdict

**Wayback does not usefully substitute for Wikipedia for this corpus.** Coverage kills it at 7%; latency and staleness confirm it. The recommendation in D403a was unproven and is now proven false.

---

## Part 2a — DB-First Path (Wired Regardless)

### What Was Done

`rag_retriever.fetch_wikipedia_summary` now checks `stop_corpus` before any network call:

1. Query `stop_corpus` for rows where `source_pages` contains a Wikipedia URL
2. Match the requested topic against `stop_title` using accent-folded comparison (D243)
3. If found, return the stored passages with zero network overhead

This implements D403a step 1 ("own DB first") which nothing previously implemented.

### Accent Folding

The DB lookup folds accents on both sides of the comparison:
- `"Île Sainte-Marguerite"` matches stored `"Ile Sainte-Marguerite"` (or vice versa)
- Uses the same `unicodedata.normalize('NFKD')` + combining-char strip as D243

### Live Demonstration

```
INFO:rag_retriever:DB-first: served 'Île Sainte-Marguerite' from stop_corpus (1134 chars, 0 network calls)
```

With `requests.get` patched to raise AssertionError, the DB-first path serves content
without triggering any network call. Verified in test `test_db_first_serves_known_title_zero_network`.

---

## Part 2b — Wayback Fallback (Wired but Gated)

### What Was Done

Despite the measurement showing Wayback is not a reliable substitute, the fallback is
wired as a last-resort path gated on `dead_host_breaker.is_host_cold()`:

- When Wikimedia is cold (429/timeout already recorded this run), attempt Wayback
- When Wikipedia returns 429 mid-request, mark cold and try Wayback
- On timeout, mark cold and try Wayback

This matches the D403a spec ("Wayback second, gated on is_host_cold").

### Provenance Labelling

Archive-sourced content is labelled through the entire return path:

```python
{
    'text': '...',
    'source': 'wayback_archive',
    'is_from_archive': True,
    'wayback_snapshot_timestamp': '20251201143022',
    'snapshot_age_days': 254,
}
```

This matches the `exhibition_checklist.py` pattern (`is_from_archive` / `wayback_snapshot_timestamp`).
Content whose snapshot is old is still labelled — the label lets a later gate make the
staleness call (a 17th-century palace description doesn't expire like an exhibition listing).

### Backwards Compatibility

`fetch_wikipedia_summary()` still returns a plain `str` (empty string on failure).
The new `fetch_wikipedia_summary_with_provenance()` returns the full dict with metadata.

---

## Out of Scope (Stated Explicitly)

**`wbsearchentities` sites are out of scope.** The Wikidata entity search at
`query.wikidata.org` is a *query API*, not a page. Wayback archives page snapshots,
not API responses to dynamic queries. The 0% REST API coverage confirms this.
Sites affected: `stop_existence_gate.py` (7 sites), `venue_resolver.py:558`,
`area_resolver.py:498`, `shortfall_search.py:216`, `dining_corpus_harvester.py:238/268`.
These remain without archive fallback because Wayback cannot serve them.

---

## What 30 Titles Cannot Support

- The 7% coverage figure has wide confidence intervals at n=30. The true coverage
  could be anywhere from 1% to 20% — none of which changes the verdict.
- We tested only English Wikipedia. French Wikipedia (`fr.wikipedia.org/wiki/X`) may
  have different Wayback coverage, but the latency and staleness problems remain.
- The corpus is skewed toward French Riviera art/landmarks, not globally representative.
  Major city landmarks (e.g. "Eiffel Tower") would likely have better Wayback coverage,
  but those are also the titles Wikipedia never fails on in the first place.

---

## Acceptance Checklist

| Criterion | Status |
|-----------|--------|
| Part 1 results table committed, harvested live | ✓ `wayback_wikipedia_probe.py` + `tests/fixtures/wayback_probe_results.json` |
| Test goes RED when fallback neutralised (D242) | ✓ `test_db_first_goes_red_when_neutralised` |
| Live run: DB-first serves summary, zero network | ✓ `test_live_db_first_no_network` |
| Provenance label present in archive output | ✓ `test_provenance_label_present` — shows `is_from_archive=True`, timestamp, age |
| Honest statement of what 30 titles cannot support | ✓ Section above |

---

## Files Changed

- `rag_retriever.py` — DB-first path + Wayback fallback + provenance chain
- `wayback_wikipedia_probe.py` — Part 1 measurement script (new)
- `tests/test_local447_db_first_and_wayback.py` — Acceptance tests (new)
- `tests/fixtures/wayback_probe_results.json` — Raw probe data fixture (new)
- `SUBMISSION_LOCAL-447.md` — This document (new)
