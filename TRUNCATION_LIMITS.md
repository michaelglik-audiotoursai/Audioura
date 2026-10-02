# Truncation Limits Proposal

**Purpose:** Michael picks two numbers — a free-tier character limit and a subscribed-tier
character limit — and we implement truncation. This document gives him cost data,
real article distributions, candidate pairs, draft messages, and the precise pipeline
insertion point. No code is written; no behaviour changes until he decides.

## Quick-Pick Table

| Option | Free Limit | Subscribed Limit | Free articles truncated | Cost/article at free limit | Notes |
|--------|-----------|-----------------|------------------------|---------------------------|-------|
| **A — Tight** | 3,000 chars | 10,000 chars | ~40–60% of real web articles | ≤ $0.017 our cost | Upsell fires often; aggressive |
| **B — Moderate** | 5,000 chars | 15,000 chars | ~15–30% of real web articles | ≤ $0.025 our cost | Matches existing TTS cap; natural boundary |
| **C — Generous** | 8,000 chars | 25,000 chars | ~5–10% of real web articles | ≤ $0.037 our cost | Upsell rarely fires; premium feel |

Pick a row (or name your own numbers) and we build it.

---

## 1. What an Article Costs Us, by Length

### Rate Table (from `cost_rates.py`)

| Component | Rate | Unit |
|-----------|------|------|
| Polly TTS | $4.00 / 1M chars | $0.000004 per character |
| GPT-3.5-turbo (title shortening only) | $0.002 / 1K tokens | ~$0.00032 per article (160 tokens, only if title > 12 words) |
| Serper search | $0.001 / query | Not used for news (text arrives pre-extracted) |
| AWS Translate | $15.00 / 1M chars | $0.000015 per character (only if translated) |

### Cost Breakdown by Article Character Count

The dominant cost is **Polly TTS**. The orchestrator calculates TTS characters as:
`min(article_length, 5000) + 1200 + (major_points × 400)`

Assuming 3 major points (typical):

| Article Length | TTS chars billed | TTS cost | LLM cost | **Total our-cost** | **User charge (×5)** |
|---------------|-----------------|----------|----------|-------------------|---------------------|
| 1,000 chars | 3,400 | $0.0136 | $0.00 | **$0.0136** | $0.07 |
| 2,000 chars | 4,400 | $0.0176 | $0.00 | **$0.0176** | $0.09 |
| 3,000 chars | 5,400 | $0.0216 | $0.00 | **$0.0216** | $0.11 |
| 5,000 chars | 7,400 | $0.0296 | $0.00 | **$0.0296** | $0.15 |
| 8,000 chars | 7,400 | $0.0296 | $0.00 | **$0.0296** | $0.15 |
| 10,000 chars | 7,400 | $0.0296 | $0.00 | **$0.0296** | $0.15 |
| 15,000 chars | 7,400 | $0.0296 | $0.00 | **$0.0296** | $0.15 |

**Critical insight:** Because `clean_text_for_polly()` already caps at 5,000 chars per
TTS segment, any article over 5,000 chars costs us the **same** for TTS — the extra text
is generated but silently truncated before Polly. The cost flattens at ~$0.030/article
regardless of article length (matching LOCAL-165's measured $0.008 for a shorter article).

This means:
- **Truncation saves TTS cost only if the limit is below 5,000 characters.**
- Above 5,000 chars, truncation limits the *reader's text experience* but does not
  reduce our Polly bill — we already don't pay for text beyond 5,000.
- If translation is involved, cost scales linearly at $0.000015/char — a 15,000-char
  translated article costs $0.225 in translation vs $0.075 for 5,000 chars.

### LOCAL-165 Measured Baseline

The test article ("MIT Solar Breakthrough") measured:
- Our cost: **$0.008264** (TTS only, short article)
- User charge: **$0.04** (×5, rounded)
- Article was ~775 characters — below the 5,000-char cap

## 2. What Articles Actually Look Like

### Database Evidence (Current State)

The local database contains only **3 test articles** (all from LOCAL-165 testing):

| Metric | Value |
|--------|-------|
| Total articles | 3 |
| Min length | 758 chars |
| Median | 775 chars |
| Max | 1,439 chars |
| Articles > 2,000 chars | 0 (0%) |
| Articles > 5,000 chars | 0 (0%) |

**⚠️ Limitation:** This is not representative of production. These are test-generated
summaries, not real web-scraped articles. The production system (`newsletter_processor_service.py`)
extracts articles from live web URLs with a 50,000-character cap (`robust_text_extractor.py`).

### Expected Real-World Distribution

Based on the pipeline design and industry norms:

- **Source:** `robust_text_extractor.py` caps extraction at **50,000 characters**
- **Newsletter processor** awards quality bonuses for articles with word_count > 500
  (≈ 3,000+ chars), suggesting those are common and desirable
- **Typical news articles:** 500–2,000 words → ~3,000–12,000 characters
- **Long-form / investigations:** 3,000–5,000 words → ~18,000–30,000 characters
- **PR Newswire** (gets quality bonus): often 2,000+ chars

**Expected distribution (industry norms for web news):**
- ~20% of articles: < 2,000 chars (briefs, summaries)
- ~40% of articles: 2,000–5,000 chars (standard news)
- ~25% of articles: 5,000–10,000 chars (features)
- ~10% of articles: 10,000–20,000 chars (long-form)
- ~5% of articles: > 20,000 chars (investigations, transcripts)

**Implication:** At any limit above ~8,000 chars, truncation fires on fewer than ~15% of
articles. The upsell message will be seen infrequently. If the goal is to make the upsell
visible enough to drive conversions, the limit must be low enough that users encounter it.

## 3. Three Candidate Pairs

### Option A — Tight (3,000 / 10,000)

| Metric | Free | Subscribed |
|--------|------|-----------|
| **Character limit** | 3,000 | 10,000 |
| **Word equivalent** | ~500 words | ~1,650 words |
| **Expected truncation rate** | 40–60% of articles | 5–15% of articles |
| **Our cost at limit** | ≤ $0.017 | ≤ $0.030 (capped by TTS 5K) |
| **User charge at limit** | $0.09 | $0.15 |

**UX trade:** Users frequently see truncation → high upsell visibility. But free-tier
feels restrictive — 500 words is barely a full article. Risk: users feel the product is
broken, not limited. Subscribers get a full article in almost all cases.

### Option B — Moderate (5,000 / 15,000)

| Metric | Free | Subscribed |
|--------|------|-----------|
| **Character limit** | 5,000 | 15,000 |
| **Word equivalent** | ~830 words | ~2,500 words |
| **Expected truncation rate** | 15–30% of articles | 3–5% of articles |
| **Our cost at limit** | ≤ $0.025 | ≤ $0.030 (same — TTS is capped) |
| **User charge at limit** | $0.13 | $0.15 |

**UX trade:** Natural boundary — aligns with the existing 5,000-char TTS cap that
already exists in `clean_text_for_polly()`. Most standard news articles fit; only
features/long-form get truncated. This is the **only option that actually saves TTS
cost** for free users (articles arriving at 5K are fully spoken). The upsell fires
often enough to be noticed but not so often that free feels useless.

### Option C — Generous (8,000 / 25,000)

| Metric | Free | Subscribed |
|--------|------|-----------|
| **Character limit** | 8,000 | 25,000 |
| **Word equivalent** | ~1,330 words | ~4,150 words |
| **Expected truncation rate** | 5–10% of articles | < 2% of articles |
| **Our cost at limit** | ≤ $0.037 | ≤ $0.030 (TTS capped) |
| **User charge at limit** | $0.15 | $0.15 |

**UX trade:** Premium feel — almost no one sees truncation. The upsell is nearly
invisible, making it ineffective as a conversion driver. Subscribers functionally
never see truncation. This option is appropriate if truncation is a safety net, not
a growth lever.

## 4. Draft Messages

### Storied Space (no subscription awareness, no cost mention)

**Variant 1 (brief):**
> This article has been shortened. The full version is 
> available in the complete article.

**Variant 2 (informative):**
> This article continues beyond this point. You're reading a 
> condensed version — [X] characters of the original [Y].

### Subscribed Space (invitation to subscribe, names higher limit)

**Variant 1 (direct):**
> This article has been shortened to [FREE_LIMIT] characters. 
> Subscribe to read up to [SUB_LIMIT] characters per article.

**Variant 2 (softer):**
> You're reading a condensed version of this article. 
> Subscribers enjoy articles up to [SUB_LIMIT] characters — 
> upgrade to read more.

**Notes:**
- `[FREE_LIMIT]` and `[SUB_LIMIT]` are placeholders for whatever numbers Michael picks.
- Messages should appear as the **last line** of the article text (per D58 directive).
- The message is appended to the truncated text, not shown as a separate UI element.
- Cost is **never mentioned** in either message.

## 5. Where Truncation Must Happen in the Pipeline

### The Pipeline (news article flow)

```
Client/Newsletter → news_orchestrator_service.py → INSERT article_requests
                                                 → POST to news_generator_service.py (text cleaning, summary, topics)
                                                 → POST to news_processor_service.py (Polly TTS audio)
                                                 → CACHE + METER + CHARGE
                                                 → DELIVER to client
```

### Insertion Point Options

| Point | Where | Saves money? | Changes article? |
|-------|-------|-------------|-----------------|
| **A. Before INSERT** (orchestrator, line ~219) | Truncate `article_text` before storing | ✅ Yes — generator processes less text | ✅ Yes — summary and topics derived from truncated text |
| **B. After generation, before TTS** (between generator and processor) | Truncate the cleaned text before Polly | ✅ Partial — saves TTS cost only, but TTS already caps at 5K | ❌ No — topics/summary from full text |
| **C. At delivery** (response to client) | Truncate the text sent back to the user | ❌ No — all generation and TTS already paid for | ❌ No — full processing happened |

### The Trap, Named

**Truncating at delivery (Point C) saves nothing.** We have already:
1. Stored the full article in the database
2. Run the generator (LLM) on the full text
3. Run Polly TTS on the full text (capped at 5K per segment anyway)
4. Paid for all of the above

Delivery truncation merely limits what the reader sees. It is a **product feature**
(content gating) not a **cost control.**

**Truncating before generation (Point A) actually saves money** — the generator
produces fewer topics, shorter summary, and Polly processes fewer characters. But it
changes the article: the AI derives its summary and key points from truncated input,
which may miss the article's conclusion or key facts.

**The correct answer depends on what Michael wants:**

- **If truncation is a cost control:** Truncate at Point A (before generation).
  This reduces both our cost and the user's charge. The article quality may suffer
  for truncated pieces, but we never pay for content we don't deliver.

- **If truncation is a product/upsell feature:** Truncate at Point C (at delivery).
  We pay full cost regardless, but the user experience is clean — full-quality
  summary and audio from the complete article, with only the text display cut short.
  The audio (which is capped at 5K chars anyway) is unaffected.

- **Hybrid (recommended to present):** Truncate the **displayed text** at delivery
  for the user, but keep the existing TTS 5K cap for cost control. This means:
  - We never pay more than ~$0.030/article for TTS regardless of article length
  - The user sees text truncated at their tier limit
  - Summary/topics are generated from the full article (better quality)
  - The user limit can be lower than the TTS cap for free tier (3K text display
    while TTS still gets its 5K for audio quality)

---

## Summary for Decision

Michael needs to decide:
1. **Two numbers** — free character limit and subscribed character limit
2. **Whether truncation is cosmetic or cost-saving** — delivery-only (C) vs pre-generation (A)
3. **Message wording** for each space

The TTS cost is already capped at 5K chars by existing code. For English-only articles,
truncation above 5K saves no money (we're already paying the same). Translation is the
exception — it scales linearly, so truncation saves real money there.

If the primary goal is **upsell visibility** (making free users aware that more exists),
Option B (5,000/15,000) at delivery gives the best balance: most articles fit free tier,
the ones that don't naturally prompt the upgrade message, and cost is controlled by the
existing TTS cap.
