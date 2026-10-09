# SUBMISSION — LOCAL-659

**Current-affairs news, round 3: newest first, real dates (never invented from
"1 month ago"), working theme queries, tighter politics gate.**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-659-news-recency` (from `subscribed` @ `f5be8ba3`)
- **Base check:** `git merge-base --is-ancestor f5be8ba3 HEAD` → exit 0 ✓

---

## The four defects (tour 557 v5, 2026-10-09)

The stops, distances and conclusion were GOOD and were NOT touched. The NEWS was
wrong four ways; each is fixed, tested offline, and demonstrated on a live run.

### Defect 1 — invented precision ("On September 9, 2026 … led a 9/11 ceremony")

The Serper date was "1 month ago"; `parse_news_date` turned that into an exact
day (today − 30) and the composer stated it as fact. 9/11 is on **September 11**,
not the 9th — the day was fabricated by arithmetic.

**Fix.** A relative date now yields only an **approximate** result; a specific day
comes **only** from the article itself.
- `resolve_news_date(raw)` → `(date, precision, phrase)`:
  - an **absolute** string ("Oct 8, 2026", "2026-10-08", an ISO datetime) →
    `(day, 'exact', '')`;
  - a **relative** string ("1 month ago", "yesterday") → `(approx_day, 'approx',
    phrase)` where `phrase` is "last month" / "about three weeks ago" — an age
    estimate for the freshness window, but **no known day**.
- `extract_published_date(html)` reads the article's own
  `<meta property="article:published_time">`, JSON-LD `datePublished`, common
  `name=date` meta variants, and `<time datetime=…>` from the **raw HTML head**
  (new `exhibition_checklist._fetch_raw_html`). `_fetch_article` now returns
  `(text, published_date)`; the research loop **upgrades** an approximate item to
  exact when the article declares a day.
- The composer prompt prints `DATE: YYYY-MM-DD (exact)` for known days and
  `WHEN: <phrase> (approximate — do NOT state a specific day)` for relative-only
  items, and forbids inventing a day for the latter.

The ISO regex was also fixed to parse an ISO **datetime** (`…-11T08:46…`), whose
`T` after the day previously broke the trailing `\b`.

### Defect 2 — not the newest (the Oct 9 governor debate was missing)

Month-old items won placement while the fresh Healey–Minogue debate was dropped.

**Fix.**
- `news_for_query` searches **`qdr:w` (past week) first**, widening to `qdr:m` then
  `qdr:y` only when a tighter window is empty.
- `_rank_items` orders items **newest first** by resolved date (dated ahead of
  undated), so the tour leads with this week's news.

### Defect 3 — the theme query returned 0 items

`'Massachusetts politics and current affairs Boston, MA' → 0` — the raw phrase was
too long.

**Fix.** `derive_theme_queries` now derives **short** queries from a stripped
subject (`_theme_subject` removes "and current affairs"/"news" and the address):

```
Massachusetts politics
Massachusetts governor
Massachusetts legislature
Massachusetts election
Boston city council
Boston mayor
```

Live, each returned 10 items (was 0).

### Defect 4 — off-theme cultural events slipped through

"the Boston Athenaeum hosted an open house … historic objects" is a cultural
event, not politics.

**Fix.** The theme gate was split and tightened:
- `_STRONG_POLITICS` (unambiguous government/elections/legislation/officials/civic
  protest) vs the broader `_THEME_WORDS`, matched on **word boundaries** (so
  "house" no longer matches "warehouse", "march" no longer matches the month);
- a `_CULTURAL_WORDS` blocklist (open house, festival, concert, exhibit, "things
  to do this weekend", open studios, restaurant, …). A cultural item is **rejected
  unless** it also carries a strong-politics term (a protest at a festival, a
  governor speaking at a gala, is still news).

---

## Tests (offline, injected network — run with no API keys)

`test_local655_current_affairs_news.py` — **58 passed**. New classes:
`TestL659Defect1ApproximateDates`, `TestL659Defect2NewestFirst`,
`TestL659Defect3ShortThemeQueries`, `TestL659Defect4TighterThemeGate`, covering:
"1 month ago" → approximate, no day; a meta `datePublished` → the exact day;
newest-first ordering; `qdr:w` before `qdr:m`; the short theme queries; open house
→ rejected; the Oct 8 debate → accepted on the State House.

### Offline suite exit codes

| suite | exit | result |
|---|---|---|
| `test_local655_current_affairs_news.py` | 0 | 58 passed |
| `tests/test_local73_news_cache.py` | 0 | 22 passed |
| `tests/test_local69_news_metering.py` | 0 | 11 passed |
| `tests/test_local658_walking_v4.py` | 0 | 22 passed |
| `test_local650_walking_route.py` | 0 | 30 passed, 3 skipped |
| `tests/test_local648_serper_research.py` | 0 | 10 passed |
| `tests/test_local599b_opening_section.py` | 1 | 3 failed — **pre-existing** |

The three `test_local599b_opening_section.py` failures reproduce with the **base
`f5be8ba3`** version of `exhibition_checklist.py`, and that suite imports none of
the APIs I changed. They are not caused by LOCAL-659.

---

## Live run (own container; ONE paid tour; cap $1.00)

Built **`local659-gen-img`** from `Dockerfile.generator` on this branch and ran a
disposable container (`docker run --rm --name local659-gen -p 5119:5000
--network development_default`). It joined `development_default` **only** to INSERT
the delivered tour as one additive `is_test` row into `development-postgres-2-1`.
**Never** `docker compose -p audioura`; **never** an `audioura-*` container; tour
cache + stop pool OFF (fresh). `./run_local659_live.sh` → `run_local659_container.py`.

- **Request:** "Walking tour in Boston dedicated to Massachusetts politics and
  current affairs, Boston, MA" — 5 stops, walking, fresh.
- **Outcome:** DELIVERED, `audio_tours` **id = 630** (`is_test = true`).
- **`audio_tours` count:** BEFORE **427** → AFTER **428** (`is_test` 362 → 363).
  Additive only. No DELETE.
- **Spend (my `run_local659_container.py` rows in `paid_api_calls`): $0.4892**
  (openai $0.3086, gemini_grounding $0.1750, gemini_tokens $0.0195, serper
  $0.0010) — **under the $1.00 cap**. The news-step diagnostics below used only
  Serper ($0.001/query) + gpt-4.1-mini, the ticket-sanctioned cheap offline
  iteration, not a second paid tour.

### Detector log (generator.log) — all four defects observed fixed

- **Defect 3:** short theme queries each returned items —
  `Massachusetts politics → 10`, `Massachusetts governor → 10`,
  `Massachusetts legislature → 10`, `Massachusetts election → 10`,
  `Boston city council → 10` (was 0).
- **Defect 2:** the **Oct 8/9 Healey–Minogue governor debate** — the item the
  ticket said was missing — was **accepted first** ("21 hours ago", exact
  `2026-10-08` via article meta).
- **Defect 1:** every ACCEPT line names its date precision **and source**:

  ```
  ACCEPT [Massachusetts State House] 'Healey, Minogue spar … governor debate'
      (CBS News, 20 hours ago) — … [date: exact 2026-10-08 via article meta]
  ACCEPT [Boston City Hall] 'Boston City Hall employee busted by feds …'
      (Boston Herald, 2 hours ago) — … [date: approx 2026-10-09 via approximate
      (relative Serper date)]
  ```

  `explicit day-dates inside news paragraphs = []` — no day was invented.
- **Defect 4:** concert, exhibit, restaurant and film festival were all **REJECTED**
  with reason `off-theme (cultural event: '<term>', no governing action)`.

### A delivery bug found on the live run — and fixed

Tour 630 **accepted 9 dated, on-theme items but delivered 0** and fell back to the
honest note. Root cause: `compose_news_sentences` was handed the **stop building
name** ("Massachusetts State House") as its subject, so gpt-4.1-mini answered
`NO MATERIAL FOUND` for a governor's-race article that never names the building.

**Fix (committed):** the composer now writes about the tour's **theme subject**
("Massachusetts politics"); the item is still **placed** at its assigned stop.
Re-verified on the news step with cheap Serper + mini reruns:

- **State House:** "*Earlier today, Massachusetts voters in Boston will consider
  nine ballot questions …*" — approximate, **no invented day** (Defect 1).
- **City Hall:** "*On October 8, 2026, Boston Mayor Michelle Wu … pledged to
  legally challenge the U.S. Postal Service's proposed … closure …*" — **exact day
  from article meta** (Defect 1), attributed (Harvard Crimson).

When news is injected, the delivery guard suppresses the LOCAL-650 "no verified
developments" note, so the news-vs-note contradiction cannot recur.

### Kiro critique (`.continuous_dev/calib/critique.sh 630 5`) — 5.5/10

Kiro flagged **no news-date or theme defect**. Its critical findings are
**stop-text corruption** outside LOCAL-659 scope: a garbled Stop 1 header
("Parkman Bandstand, a significant benefactor whose $5 million bequest …") and a
garbled Stop 3 (City Hall) body with dangling pronouns. The ticket states the
stops/distances/conclusion were GOOD and must not be touched; these are
pre-existing stop-generation defects, not news defects. The "borderline leftover
scaffolding" line Kiro noted is the **pre-fix** honest note; with the compose-
subject fix it is replaced by the dated news paragraphs shown above.

---

## Files changed

- `current_affairs_news.py` — date precision (`resolve_news_date`,
  `extract_published_date`, exact-vs-approximate), newest-first `_rank_items`,
  `qdr:w` first in `news_for_query`, short `derive_theme_queries`/`_theme_subject`,
  split politics/cultural theme gate, compose about the theme subject.
- `exhibition_checklist.py` — new `_fetch_raw_html` (raw head for date metadata).
- `generate_tour_text.py` — ACCEPT log line now prints date precision + source.
- `test_local655_current_affairs_news.py` — four new LOCAL-659 test classes.
- `run_local659_container.py`, `run_local659_live.sh` — isolated live-run harness.

## Process

- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
  `.continuous_dev/STATUS.md`.
- Committed after each step; branched from HEAD @ `f5be8ba3`.
- No DELETE; no GCloud. Rows: additive `is_test` only.
