# Request to Kiro Amazon-Q — Three Things to Resolve on Newsletter/News-Article Services
**From:** Claude (via Sir Michael)
**Date:** 2026-06-01
**Services in scope:** `newsletter_processor_service.py`, `background_article_processor_service.py`, `content_extraction.py`, `news_generator_service.py`, `news_processor_service.py`
**Status:** Two diagnostic questions that must be answered before assigning ownership, plus one design correction that should be implemented regardless of those answers.

---

## Purpose and the logic behind this request

Sir Michael ran four tests; #3 and #4 concern the news/newsletter pipeline. Earlier analysis concluded #3 and #4 were "not a services bug" on the grounds that the two articles delivered to the phone (`ee72a68b`, `228b694d`) carry **no URL** in the database and were therefore raw-text submissions from the mobile app. That conclusion is premature. As shown below, there is a services code path that produces records with **exactly that signature** — text present, URL absent, content extracted on the server — and that path has a known wrong-section failure mode. So "no URL on the record" cannot, by itself, establish that the mobile app sent the wrong text.

This document does three things:
1. **Item 1** defines the single decisive test that determines whether #4 (wrong article text) is a services extraction bug or a mobile submission bug. We are not asserting it is services; we are asserting the current evidence does not rule services out, and naming the one lookup that settles it.
2. **Item 2** defines the test that determines whether #3 (only 2 of 5 articles delivered) is a server-side generation/deliverability problem or a mobile download-loop problem.
3. **Item 3** is a design correction that is correct **independently** of Items 1 and 2: the newsletter must offer the user only the articles it can actually deliver. This addresses Sir Michael's direct objection — "if only 2 were accepted, why did services return 5?"

A note on the conceptual model, because it frames everything below. The value the app uses to fetch an article is its **article_id**. The app downloaded the right id, and the translation step faithfully translated whatever text was bound to that id. The wrong content was already bound to the id at the moment it was **created**. Therefore the error — if it is a services error — lives at **creation/extraction time**, not at download or translation time. Timing, async counters, and the translation path are not relevant to #4; only "what text got bound to this id, and who extracted it" is relevant.

---

## Item 1 — Decisive test for #4 (wrong article text)

### The two possible flows, and why only one has a "place for error"
Sir Michael's reasoning is correct with one hidden branch:

- **Branch A — the app passes final text, services convert it to audio.** In this branch there is genuinely no legitimate place for error. Text in, audio out, deterministic. If the audio content is wrong, services received the wrong text, and #4 is a mobile-side bug.
- **Branch B — the app passes a URL and the *server* fetches and extracts the article text.** In this branch there is a very real place for error: the extraction step. If the server extracts the wrong section of the page, the wrong text gets bound to the article id, and #4 is a services bug — even though the app did nothing wrong beyond sending a URL.

So the entire question reduces to: **which branch ran for `ee72a68b` and `228b694d`?**

### Why "no URL in the DB" does not answer it
There is a services path — `background_article_processor_service.py` — that runs Branch B and leaves **no URL on the record**:

```python
# background_article_processor_service.py:73
article_content = self.fetch_article_content(article_info['article_url'])   # server fetches the URL
...
# background_article_processor_service.py:142-156  — stores text only, no URL column written
cursor.execute("""
    UPDATE article_requests
    SET article_text = %s, article_topics = %s
    WHERE article_id = %s
""", (article_content['content'].encode('utf-8'), ..., article_id))
```

And the extractor it uses is naive enough to grab the wrong section:

```python
# background_article_processor_service.py:103-136
content_selectors = ['article', '.article-content', '.post-content', '.entry-content', 'main']
content = ""
for selector in content_selectors:
    element = soup.select_one(selector)      # FIRST match only
    if element:
        content = element.get_text(strip=True)
        break
if not content:
    content = soup.get_text(strip=True)      # whole-page fallback
```

`select_one` returns only the **first** element matching each selector. On a long article page that stacks multiple `<article>` or `.post-content` blocks (a featured block above the body, or a multi-section newsletter-style article), this captures the wrong block. The text Sir Michael received — the "Analysis of 500+ verified reviews across Gartner and G2… Einstein… ROI…" passage — is on-topic for the resolved article ("the last great head-fake in software history," an enterprise-software/AI piece). That strongly indicates he got a **real but wrong section of the correct article**, which is precisely the `select_one`-first-match failure mode, not "unrelated pasted text."

Because Branch B writes a record with text and no URL, the record is **indistinguishable** under the "has URL?" test from a Branch A pasted-text record. The test that was used to assign #4 to iOS cannot actually tell the two branches apart.

### The lookup that settles it
Please determine, for article ids `ee72a68b…` and `228b694d…`:

1. **Did the server make an outbound HTTP GET to reloadnyc (or the resolved `the-last-great-head-fake-in-software-history` URL) at creation time (~00:50 and ~00:53)?** Check the services egress / access logs.
   - **GET present** → Branch B → the server extracted the text → #4 is a **services extraction bug**. Proceed to the fix below.
   - **No GET; the text arrived already populated** → Branch A → the text was produced upstream of services → #4 is a **mobile-side** bug, and the original iOS assignment stands.

2. **Inspect the `/generate-article` request body** that `news-orchestrator` received for these two ids. `background_article_processor_service.py:165-170` calls the orchestrator with `article_text` and `request_string`. The question is where that `article_text` originated — the server's own `fetch_article_content` (Branch B) or the client payload (Branch A). The presence/absence of a preceding server fetch (lookup #1) answers this directly.

3. **Inspect the `article_requests` row** for these ids: is *any* source/url column populated, and what is the status history? A `processing → completed` transition driven by `background_article_processor_service.update_article_status()` is itself a fingerprint of Branch B.

This is a few minutes of log/DB inspection and removes all guesswork. We genuinely do not know which way it will resolve — we are only stating that the evidence so far does not justify ruling services out.

### If Item 1 resolves to services — the fix
1. **Replace the `select_one` first-match cascade in `fetch_article_content`.** Either select the **largest / highest text-density** candidate block instead of the first, or — better — reuse the platform-aware extractor that already exists in `content_extraction.py` (`extract_newsletter_content()` / `extract_generic_content()`), which is materially more robust than the five-selector cascade in `background_article_processor_service.py`.
2. **Persist the resolved source URL on the article record** at creation. The fact that a server-extracted article currently looks identical to a pasted-text article is itself what made this hard to triage; storing the URL makes every future case a one-query answer.
3. **Return the resolved source URL to the client** so the player can show "Generated from: &lt;url&gt;" and a wrong extraction is visible immediately rather than discovered by listening.

---

## Item 2 — Test for #3 (only 2 of 5 articles delivered)

### What we can and cannot conclude from the logs provided
Be aware: the two iPhone logs supplied (`log_iphone_06012026_2045.txt`, `log_iphone_06012026_2058.txt`) do **not** contain the test-#3 "download all 5" events. The 20:45 log ends at the home list and "Loading 34 articles"; the 20:58 log is the single-article (#4) activity. So the 2-of-5 outcome cannot be confirmed or refuted from this evidence, and "newsletter 280 has 5 articles" proves only that five were *created*, not that all five are *deliverable*.

### The two candidate causes
- **Generation-time loss.** In `newsletter_processor_service.py`, each detected article runs through a loop (line 1582) where it can be dropped into `failed_articles[]` for several reasons — advertising URL/content (lines 1591-1598, 2004), insufficient content < 200 chars (1896-1897), content too short < 100 bytes (2010), link error (1633), browser-automation error (1758), DB constraint (2108). If three of the five tripped these, only two ever became deliverable. This is a **services** outcome (possibly correct filtering, possibly over-aggressive thresholds).
- **Download-loop loss.** Alternatively, all five are deliverable server-side and the mobile "download all" loop only issued/completed two requests. This is a **mobile** outcome.

### The test that settles it
For each of newsletter 280's five article ids, call the delivery endpoint directly:

```
GET http://192.168.0.218:5012/download/<article_id>?language=ru
```

- If **3 return errors / non-200 / empty ZIP** → #3 is (at least partly) a **services** generation/translation/packaging problem. Then check the server log for which `failed_articles` reason fired for the three, and whether the advertising/short-content thresholds are wrongly rejecting legitimate ReloadNYC bodies.
- If **all 5 return 200 + valid ZIP** → the loss is the **mobile** download loop, and that part of #3 is correctly an iOS fix.

The black-screen-on-Refresh is a separate, clearly mobile (iOS) defect and is not disputed.

---

## Item 3 — Required design correction: offer only the deliverable list (implement regardless of Items 1–2)

### The requirement
Sir Michael's requirement, stated precisely: **the list offered to the user must be the deliverable list, not the candidate list. Services must return only the articles that actually reached a ready/deliverable state. Services must NOT return all five with per-article status for the app to display "3 unavailable" — that is confusing to users.** If an article cannot be delivered, the user should never see it or be invited to download it.

### Why this is happening now — the code
The newsletter-processing endpoint currently returns **both** the candidate count and the created count in the same response:

```python
# newsletter_processor_service.py:2200-2209
response_data = {
    "status": "success",
    "newsletter_id": newsletter_id,
    "articles_found": len(article_urls),        # = 5  (candidates detected)
    "articles_created": articles_created,        # = 2  (actually generated)
    "articles_requiring_subscription": articles_requiring_subscription,
    "articles_failed": len(failed_articles),
    "failed_articles": failed_articles[:3],
    "message": f"Newsletter processed: {articles_created} articles created, ..."
}
```

`articles_found` (5) is the **detection** count; `articles_created` (2) is the **deliverable** count. Whichever count/list the app currently presents for "download all," the user ended up being offered five. Services is exposing the candidate number as if it were the deliverable number.

Importantly, the **correct, deliverable-only query already exists** elsewhere in the same service:

```python
# newsletter_processor_service.py:757-765  (get_articles_by_newsletter_id)
SELECT ar.article_id, ar.request_string, ar.url, ar.created_at, ar.status, ...
FROM article_requests ar
JOIN newsletters_article_link nal ON ar.article_id = nal.article_requests_id
JOIN news_audios na ON ar.article_id = na.article_id          -- must have audio
WHERE nal.newsletters_id = %s AND ar.status = 'finished'        -- must be finished
ORDER BY ar.created_at DESC
```

This query already enforces exactly the requirement: it returns only articles that are `status = 'finished'` **and** have a `news_audios` row (i.e., audio actually exists). So the platform already knows how to compute the deliverable list — it just isn't the thing being surfaced after processing.

### Suggested changes
1. **Make the deliverable list the single source of truth for what the user is offered.** After processing, the article list the app shows for a newsletter should be driven by the `get_articles_by_newsletter_id` query (status = 'finished' + has audio), not by `articles_found`. If the app currently reads the list/count from the processing response, switch it to call `get_articles_by_newsletter_id` and render exactly those rows.

2. **Stop exposing the candidate count as a user-facing number.** In the processing response (lines 2200-2209), remove `articles_found` from anything the app uses to build the user-facing list or count, or rename it to an internal/diagnostic field that the app does not display. The only count the user should see is the count of delivered articles. (`failed_articles` / `articles_failed` may be retained server-side for logging and for tuning the filters in Item 2, but per the requirement they must **not** be surfaced to the user as "unavailable" entries.)

3. **Reconcile the status vocabulary.** There is a vocabulary mismatch that must be verified or this fix will silently under- or over-count: the newsletter delivery queries filter `ar.status = 'finished'` (lines 659, 763), while the single-article generator sets `status = 'ready'` (`news_generator_service.py:603`), and the background processor uses `'completed'` (`background_article_processor_service.py:88`). Please confirm which status value canonically means "deliverable to the user," ensure every successful generation path transitions the row to that one value, and ensure the deliverable query filters on it. If newsletter articles end in `'finished'` but some success paths leave rows in `'ready'`/`'completed'`, the deliverable list will be wrong even after changes 1 and 2.

4. **Guarantee the offered count equals what is downloadable.** After the change, "download all" for a newsletter must iterate exactly the rows returned by the deliverable query, so the number offered and the number delivered are identical by construction. This makes the "why did it say 5 but give me 2" class of report impossible going forward.

---

## Summary for triage
| Item | Question / requirement | How it is resolved | Owner determined by |
|---|---|---|---|
| 1 — #4 wrong text | Did the server extract the text (Branch B) or receive it (Branch A)? | Egress GET at ~00:50 + `/generate-article` payload + `article_requests` row | The lookup; services if a server fetch occurred |
| 2 — #3 only 2/5 | Are all 5 deliverable server-side? | `GET :5012/download/<id>?language=ru` for each of the 5 ids | Services if ≥1 fails; mobile if all 5 succeed |
| 3 — offer deliverable list only | Return only ready/deliverable articles; never offer undeliverable ones | Drive the list from `get_articles_by_newsletter_id` (status='finished' + audio); stop surfacing `articles_found`; reconcile status vocabulary | Implement regardless — this is a services-side correctness fix |

We are not claiming #3 and #4 are services bugs. We are claiming (a) the current evidence does not justify ruling services out — Item 1 names the lookup that decides #4, Item 2 names the test that decides #3 — and (b) Item 3 is a services correctness fix that is warranted on its own terms, because the platform already computes the deliverable list and simply isn't the thing being offered to the user.
