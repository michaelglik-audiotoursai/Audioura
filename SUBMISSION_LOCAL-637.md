# SUBMISSION — LOCAL-637

**Venue resolution must survive rate limits and never take a band for a museum**
(National Gallery and Wallace Collection refused in Bench R6)

- **Branch:** `LOCAL-637-resolver-robustness`
- **Base:** `subscribed` @ `841b073` (`git merge-base --is-ancestor 841b073 HEAD` → 0)
- **Agent:** Mac Mini Kiro

---

## The two Bench R6 failures

Both tours ended with *"We could not find enough verified material about …"*.

1. **National Gallery** (resolved to **Q180788**, 389 works, earlier in the same run):
   ```
   [DEAD-HOST] Marked cold: wikimedia (HTTP 429 on _search_entities)
   _search_entities failed: HTTP 429 for query 'London'
   Single candidate Q180788 (National Gallery) failed city validation for 'London'
   No Wikidata candidates
   ```
   A **rate limit** rejected an already-resolved, correct venue. Six tours ran at once.

2. **Wallace Collection** (resolved **Q1516598**): `[story_miner] Sitelink EN: 'Wallace Collection (band)'`,
   accepted "on venue-name match". A **music band's** Wikipedia article became the museum's corpus; the
   real site pages were `EXCLUDED … url_path_nonwork`.

---

## Root causes (both confirmed, the second verified live against Wikidata)

### 1. One 429 sank an already-resolved museum

`_search_entities` marked the Wikimedia host **cold on the first 429** (no retry, no `Retry-After`, no
backoff). The dead-host breaker's per-tour cold mark **never expired**, so every later Wikidata call in
that tour short-circuited to `None`. When the single high-confidence candidate (Q180788, 389 works) reached
`_validate_city_match('London')`, `_geocode_city` returned `(None, None)` because the host was cold — and
`_validate_city_match` / `_is_located_in` **conflated "could not verify" with "verified not in city"**, both
returning `False`. The museum was discarded on a rate limit.

### 2. The resolver resolved the WRONG QID (the hint was right)

Verified live on Wikidata:

| QID | label | P31 | enwiki sitelink | works |
|-----|-------|-----|-----------------|-------|
| **Q1516598** | Wallace Collection | Q215380 (musical group) | **Wallace Collection (band)** | 0 |
| **Q1327919** | Wallace Collection | Q207694 (art museum) | Wallace Collection | 674 |
| Q106500505 | The Wallace Collection | — | *(Vanity Fair caricature)* | 0 |

`wbsearchentities` for **"The Wallace Collection"** (with "The") returns **only the band and the caricature** —
the museum is labelled "Wallace Collection" (no "The") and is **absent**. `_normalise_venue_name` never
stripped the leading "The", so the museum was never searched; the band (0 works, not museum-typed) won the
no-museum-typed collection-ranked fallback, and its own `(band)` enwiki sitelink became the museum's corpus.

---

## Deliverables

### 1. Rate limits (`venue_resolver.py`, `dead_host_breaker.py`)

- **`_request_with_backoff()`** — one retry path for every Wikidata/Wikipedia GET. Retries `429` and
  `500/502/503/504` and timeout/connection errors, **3 retries with 2 s / 5 s / 10 s backoff + jitter**, and
  **honours `Retry-After`** (seconds or HTTP-date, capped at 15 s). The host is marked cold **only after the
  retries are exhausted**. `_search_entities` and the SPARQL `fetch_venue_works` both route through it.
- **Dead-host cool-down** — the per-tour cold mark is now a **short cool-down (20 s)**, not a tour-long death
  sentence. One transient 429 no longer disables Wikidata for the rest of the tour; the host is retried once
  the cool-down elapses. The per-tour cold set is a timestamped dict, so LOCAL-572 concurrency isolation
  (a mark in one worker thread is visible tour-wide; two concurrent tours stay independent) is preserved —
  all 26 existing dead-host tests still pass.
- **UNKNOWN city validation** — `_is_located_in` and `_validate_city_match` are now **tri-state**:
  `True` (confirmed in city), `False` (verified NOT in city), `None` (could-not-verify: 429/5xx/timeout).
  A rate limit is `None`, never `False`.
- **Keep the high-confidence candidate on UNKNOWN** — when the single resolved candidate's city validation is
  `None`, `resolve_venue` **keeps** it if it is high-confidence (`_is_high_confidence_candidate`: its label
  carries the venue's distinctive tokens **and** it holds ≥ 25 catalogued works). This is exactly the National
  Gallery case: Q180788, label match, 389 works → kept under a 429 instead of discarded.

### 2. Disambiguation — never a band for a museum (`venue_resolver.py`, `story_miner.py`)

- **`_normalise_venue_name`** adds a **leading-article-stripped variant** ("The Wallace Collection" also
  searches "Wallace Collection"); `resolve_venue` unions that variant's hits so the museum surfaces for the
  P31 museum-type filter. Verified: `resolve_venue("The Wallace Collection", "London")` → **Q1327919**
  (wallacecollection.org, London coordinates, Sir Richard Wallace).
- **Parenthetical-qualifier guard** in `story_miner`: a Wikipedia title (the venue QID's **own** enwiki
  sitelink, or any fuzzy fallback) whose parenthetical qualifier names a non-museum thing — `(band)`,
  `(album)`, `(film)`, `(song)`, `(TV series)`, `(video game)`, `(novel)`, … — is **rejected** for a museum
  venue. A museum-compatible qualifier (`(museum)`, `(gallery)`, `(London)`, `(Nice)`, `(institution)`) or no
  qualifier is still accepted. Applied both where the exact sitelink is read and in the title-acceptance loop,
  so even if a namesake QID enters, its `(band)` article can never become a museum's corpus.

### 3. Tests (offline/mocked, on the real log lines + QIDs, with injected 429s)

- **`test_local637_resolver_robustness.py`** (new, 17 tests):
  - `_request_with_backoff`: 429→200 recovers without marking cold; all-429 marks cold **only after** 4
    attempts; `Retry-After` honoured; `_parse_retry_after`.
  - `_is_located_in` 429 ⇒ `None`; `_validate_city_match` UNKNOWN on geocode failure; `False` only when
    verified not-in-city.
  - **National Gallery Q180788 (389 works) KEPT** under UNKNOWN validation; a 0-work candidate is NOT kept on
    a stall.
  - Dead-host per-tour mark is a cool-down (cold within it, retriable after it elapses; Wikimedia bucket
    shared).
  - Parenthetical guard rejects band/album/film/song/TV series/video game/novel; accepts
    museum/gallery/London/Nice/institution; `resolve_venue` prefers museum **Q1327919** over band Q1516598.
- **`test_local636_national_gallery.py`** updated: the old `test_429_does_not_retry` (stale policy) is
  replaced by `test_429_retries_then_recovers` and `test_429_exhausted_marks_cold_and_returns_none`.

#### Full test battery — all green

| group | result | exit |
|---|---|---|
| `tests/test_local60* 61* 62*` | 378 passed | 0 |
| `test_local63*` (root) | 105 passed | 0 |
| `tests/test_local63*` | 16 passed | 0 |
| `tests/test_lead_*` | 5 passed | 0 |
| `test_local590_*` (root) | 42 passed | 0 |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | 0 |
| `test_local636` + `test_local637` | 26 passed | 0 |

### 4. Live (own container, cache + pool off, hard cap $1.30 with reserve gate)

Built an **own disposable container** `local637-gen` (`docker run --rm`, spare port **5098**, network
`development_default`, image `local637-gen-img`). **No `docker compose -p audioura`; no `audioura-*`
container renamed or replaced** (all 13 service containers verified still running). Harness:
`run_local637_live.sh` + `run_local637_container.py`.

1. **PAID — The Wallace Collection, London, 3 stops.** DELIVERED, 5641 chars, 3 stops:
   - *The Laughing Cavalier* (Frans Hals), *The Lady with a Fan* (Velázquez), *Madame de Pompadour* (Boucher)
     — all **genuinely at the Wallace Collection**. Resolved to the **MUSEUM** (Q1327919); **no `(band)`**.
   - `tour_total = $0.6634`; stored as additive `is_test` row **id 527**. **Only one paid tour** (no second).
   - `detectors.py 527 3 "The Wallace Collection, …"` → `527: 0 detector failure(s)` (exit 0).
   - `critique.sh 527 3` → **6.5/10**; **criterion-8 location PASS** — the critic confirms all three works are
     genuinely at the Wallace Collection (museum, not band). Its flagged defects (a provenance phrasing bug,
     no spoken admission line, a conclusion that omits Boucher) are narration/text issues **outside the
     LOCAL-637 resolver scope**.
2. **FREE — resolver-only National Gallery × 3 under an injected 429** (no paid calls): **3/3 resolved to
   Q180788** (nationalgallery.org.uk, London coordinates). The retry fired (`429 — retry 1/3`) and recovered
   each time — the exact Bench R6 fix, proven live.

**Metered total $0.6332** (openai $0.4594, gemini_grounding $0.0980, gemini_tokens $0.0328, serper $0.0430,
preflight $0.0301) — well under the $1.30 cap.

#### Database — additive `is_test` only

| | before | after |
|---|---|---|
| `audio_tours` total | 332 | 333 |
| `audio_tours` is_test | 269 | 270 |

Exactly **+1** additive `is_test` row (id 527, `is_test=true`). **No DELETE. No GCloud.** The own container
was removed by `--rm` and its image deleted; the 13 `audioura-*` service containers were untouched.

Artifacts: `submission_artifacts/local637_live/` (`critique_527.md`, `detect_527.txt`, `tour_527.txt`);
full log in `tours/local637_live/local637_live.log`.

---

## Files changed (owned only)

| file | change |
|---|---|
| `venue_resolver.py` | `_request_with_backoff` + `_parse_retry_after`; `_search_entities` and SPARQL via the helper; tri-state `_is_located_in` / `_validate_city_match`; `_is_high_confidence_candidate` + keep-on-UNKNOWN in `resolve_venue`; leading-article-stripped variant + union in `resolve_venue` |
| `dead_host_breaker.py` | per-tour cold mark is a short cool-down (timestamped dict + `_purge_expired_tour_locked`); concurrency isolation preserved |
| `story_miner.py` | non-museum parenthetical-qualifier guard (`_title_qualifier_rejects_museum`) at the sitelink read and title-acceptance loop |
| `test_local637_resolver_robustness.py` | new (17 tests) |
| `test_local636_national_gallery.py` | 429 tests updated to the new retry policy |
| `run_local637_live.sh`, `run_local637_container.py` | live acceptance harness |
| `submission_artifacts/local637_live/` | live artifacts |

Not edited: `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, `.continuous_dev/STATUS.md`.
