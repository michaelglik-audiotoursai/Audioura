# SUBMISSION — LOCAL-741

**Newsletter link → English Wikipedia rejected as "Non-English"; a single-article link must give that article**

- **Branch:** `LOCAL-741-newsletter-language`
- **Base:** `subscribed` @ `98cc6dc6` (verified ancestor: `git merge-base --is-ancestor 98cc6dc6 HEAD` → 0)
- **code_sha:** `79f1994050b96d5437fc2d7bddbce4f931480548`
- **Files:** `newsletter_processor_service.py`, `tests/test_local741_newsletter_language.py`, `docker-compose.local741.yml`

---

## Problem (Michael's review A3, 2026-10-22)

Generate → Newsletter with `https://en.wikipedia.org/wiki/Boston`. LEAD replayed the app request
(`newsletter_url`, `user_id`, `max_articles 10`, `max_depth 2`, `days_limit 7`): `articles_found 10,
articles_created 0`, every page `REJECTED: Non-English content detected - avoiding TTS costs` — although the
logs showed English titles ("Mayor–council government", "Northeastern United States", 95,666 chars). Two
defects: (A) one pasted ARTICLE became ten crawled linked pages; (B) a fully English article was rejected
as non-English.

## Root cause

**(B) Language check.** `is_english_content(text)` returned `False` on the **first** non-Latin character
anywhere in the text:

```python
for pattern in non_english_patterns:        # CJK / Cyrillic / Hebrew / Arabic / …
    if re.search(pattern, text):            # ANY single match → reject
        return False
```

A Wikipedia article's extracted text carries the **interlanguage-link sidebar** — the title written in
dozens of languages (中文, Русский, العربية, עברית, …). A handful of those characters tripped the check and
rejected the entire 95k-char English body. (The ASCII-ratio branch had the same single-character fragility.)

**(A) Crawl.** The linked-article pattern detector + fallback clickable-URL extraction ran for **every** URL,
so a single-article page was scraped for links and produced up to `max_articles` linked pages.

## Fix (`newsletter_processor_service.py`)

1. **`is_english_content()` rewritten** to judge the cleaned article **body** (strips this service's own
   `NEWSLETTER:/ARTICLE:/CONTENT:` wrapper, which is English boilerplate), with two signals:
   - **Script prevalence** — reject only when non-Latin-script letters are **≥ 25%** of all letters
     (denominator is letters only). A Russian/Chinese body is ~100% → rejected; an English article with an
     interlanguage sidebar is a few percent → passes. No single character can reject an article.
   - **Function-word dominance** — for Latin-script foreign prose (e.g. French), where signal 1 reads ~0,
     defer to the shared deterministic `language_guard.is_in_tour_language(sample, "en")` (stopword ratio).
     Conservative: English with loanwords/accented proper nouns passes.

   The cost guard is intact for genuinely non-English articles. (It is in fact *stricter* than base: base
   accepted French; the fix rejects it.)

2. **`is_single_article_page(url, soup)` added** and gates the linked-article crawl. Heuristic (simple,
   URL-first): the page is treated as a **newsletter** (crawl its links) **only** when it clearly looks like
   one — a known newsletter/email host (`mailchi.mp`, `view.email.`, `substack.com`, Constant Contact, …), a
   newsletter/issue/archive path (`/issue`, `/newsletter`, `/archive`, …), or a bare site root. Everything
   else — an encyclopaedic host such as Wikipedia, or a normal `/section/slug` story URL — is a **single
   article**: that article is processed as the first (and only) result; no linked pages follow. Fail-safe
   defaults to single-article (the cheaper behaviour).

3. **D670 plan length** is unchanged and already correct: the newsletter service forwards the full article
   text to the news orchestrator; per-plan truncation (`article_char_limit`) is applied downstream in
   `news_processor_service.process_audio()` via `article_truncation.truncate_for_user()` — the single source
   of truth for both the read text and the synthesised audio. Confirmed below for Free (5,000) and $10 Pack
   (10,000).

## Tests (`tests/test_local741_newsletter_language.py`)

Pure-function tests, no network/DB. `python3 -m pytest tests/test_local741_newsletter_language.py` → **13 passed.**

- **English Wikipedia (Boston) fixture passes the language check** — English body + a non-Latin
  interlanguage sidebar.
- **Red test (verified):** the same Boston fixture run against the **base** `is_english_content` returns
  `False` (rejected) — so the test fails on base, passes after the fix:
  ```
  BASE  is_english_content(BOSTON)  = False   # the defect
  FIXED is_english_content(BOSTON)  = True
  BASE  is_english_content(FRENCH)  = True     # base wrongly accepted French
  FIXED is_english_content(FRENCH)  = False
  BASE  is_english_content(RUSSIAN) = False
  FIXED is_english_content(RUSSIAN) = False
  ```
- **French and Russian fixtures still rejected** (cost guard kept).
- **Single-article vs newsletter URLs:** Wikipedia / `/section/slug` → single article; `mailchi.mp`,
  `view.email.*`, `/newsletter/issue-42`, bare root, Substack archive → newsletter.

Related suites regression-free:
`pytest tests/test_local741_newsletter_language.py tests/test_local616_scraped_language_guard.py
tests/test_local193_article_truncation.py tests/test_local708_article_length_per_plan.py` → **77 passed.**

## Live test

Own isolated stack `-p local741` (`docker-compose.local741.yml`): newsletter-processor + news-orchestrator +
news-generator + news-processor + polly-tts, built from THIS worktree, on spare 547xx ports, all writing
**only** to `audiotours_test` on the shared dev postgres. Never `-p audioura`, never touched `audioura-*`
containers. TTS routed to the host-native Kokoro engine (same as the shared stack) → $0 TTS.

Request (the app's replay): `POST /process_newsletter`
`{newsletter_url: https://en.wikipedia.org/wiki/Boston, user_id: local741_test_user, max_articles: 10,
max_depth: 2, days_limit: 7, test_mode: true}`

Result:
```json
{ "status": "success", "articles_created": 1, "articles_requiring_subscription": 0,
  "_diagnostic": { "articles_detected": 1, "articles_failed": 0, "failed_articles": [] } }
```
Service log: `[SINGLE-ARTICLE] …/wiki/Boston … skipping linked-page crawl` and
`✅ CONTENT VALIDATION PASSED: 170920 bytes - HIGH QUALITY ENGLISH CONTENT`; `FINAL RESULTS: Found=1, Created=1, Failed=0`.

**Row counts (audiotours_test), before → after:**

| table | before | after | Δ |
|---|---|---|---|
| article_requests | 19 | 21 | +2 (newsletter quota-debit row + Boston article) |
| newsletters | 0 | 1 | +1 |
| newsletters_article_link | 0 | 1 | +1 |
| news_audios | 0 | 1 | +1 (audio synthesised, $0 Kokoro) |
| audio_tours | 0 | 0 | 0 (untouched; no DELETE, no purchase-row changes — D690) |

**D670 per-plan length** on the real Boston article text (`article_truncation`), simulating the ~95k-char body:

| plan | delivered chars | ≤ limit | on-screen notice |
|---|---|---|---|
| Free (5,000) | 5,000 | ✓ | "Shortened to about 1½ pages. A larger plan plays articles up to about 5 pages — See plans" |
| $10 Pack (10,000) | 10,000 | ✓ | "Shortened to about 3 pages. A larger plan plays articles up to about 5 pages — See plans" |

(The spoken notice comes from the same module, `build_spoken_notice`, exercised by `test_local708`.)

**Cost:** TTS $0.00 (Kokoro). Total run = one `news_generate` LLM call = **$0.0312** (cost_ledger, audiotours_test). ≤ $0.30 ✓.

Stack torn down (`docker compose -p local741 … down`); shared `audioura-*` stack intact.

## Notes / scope

- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`. No ClickUp status change.
- The cost guard remains in force for genuinely non-English articles; the product still treats this path as
  English-only. If other languages are to be supported here, that is a LEAD decision (the French/Russian
  rejection tests pin the current contract).
