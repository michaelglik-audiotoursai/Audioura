# SUBMISSION — LOCAL-708: Article length per plan (text AND audio)

**Branch:** `LOCAL-708-article-length-per-plan` (from `subscribed`, base `f2e16ba3`)
**Agent:** Mac Mini Kiro
**Design of record:** D670 (Administrator/Curator ≈ 5 pages)

---

## Problem (D670)

Michael wants the Administrator plan to listen to (and read) articles up to
~5 pages. Before this change:

- The **audio** was hard-capped at **5,000 characters** in
  `clean_text_for_polly()` — so no plan could ever hear more than ~1.5 pages.
- The **text** limit in `article_truncation.py` keyed on the retired wallet
  tiers (`free` / `ppu` / `unlimited`), not the D613 plans
  (`l1`, `l2`, `l3`, `l4`, `admin`, `tester`).

## What changed

Article length is now a **per-plan number in the `plans` table**, and it governs
**both** the text the listener reads **and** the audio they hear. One truncation,
one source of truth.

### 1. Migration `039_article_char_limit.sql` (additive, idempotent — LEAD applies)

Adds `plans.article_char_limit INTEGER` and sets, per D670:

| plan | article_char_limit |
|------|-------------------:|
| l1     |  5,000 |
| l2     |  5,000 |
| l3     | 10,000 |
| l4     | 15,000 |
| admin  | 15,000 |
| tester | 15,000 |
| free / ppu / unlimited (legacy) | 5,000 |

`ADD COLUMN IF NOT EXISTS` + per-plan `UPDATE`. No DELETE, no DROP, safe to
re-run. A plan with no value (NULL) or an un-migrated DB falls back to the
**code default of 5,000**.

### 2. `article_truncation.py` — resolve the listener's plan

`truncate_for_user(text, user_id)` now resolves the device's **plan level** with
the **same entitlement lookup the tour quota uses**
(`subscription_levels.get_device_state(user_id) → level`), then reads that plan's
`article_char_limit`. A device with no row is L1 (install default).

- **Code default 5,000** on NULL / missing column / unknown level / empty user /
  any DB error (fail-safe: smallest limit).
- **Boundary rules unchanged**: cut at the last sentence boundary; if that
  discards >15% of the allowance, fall back to the last word boundary; the
  appended notice never pushes the text back over the limit.
- **Notices unchanged** (D58 — no cost, no dollar figure): an entry plan (limit
  equal to the floor value) gets the invitation that names the higher ceiling; a
  higher plan gets the limit-only notice.
- **Env overrides remain a GLOBAL CEILING** (emergency throttle, no redeploy):
  any per-plan value is clamped to `NEWS_SUBSCRIBED_CHAR_LIMIT` (default 15,000);
  `NEWS_FREE_CHAR_LIMIT` (default 5,000) is the floor/entry value shown in the
  upsell. Lowering the ceiling throttles every plan at once.
- **Backward compatible**: `truncate_article_text(text, tier)` and
  `get_char_limit_for_tier(tier)` still accept the legacy wallet strings so
  existing callers/tests keep working.

### 3. `news_processor_service.py` — audio follows the text limit

- Removed the fixed **5,000-char cap** in `clean_text_for_polly()`. That function
  now only cleans (HTML/entities/URLs/whitespace); it imposes no length cap.
- `process_audio()` computes `display_text = truncate_for_user(full_text, secret_id)`
  **once, before** generating audio. The full-article audio (`audio-99`) is
  synthesised from that **plan-truncated text** (previously it voiced the
  untruncated `full_text` and relied on the removed 5,000 cap). The HTML the user
  reads and the audio they hear now come from the same truncated source.
- The **polly-tts 2,000-char split is reused, not duplicated**: a 15,000-char
  admin article is split by `polly_tts_service` and joined into **one** MP3.

## Tests

`tests/test_local708_article_length_per_plan.py` (no live DB — the resolution
path is driven against a fake connection/cursor):

- Per-plan limits resolved from the table: **l1 5k, l3 10k, l4 15k, admin 15k, tester 15k**.
- Missing `article_char_limit` column → **5,000**; NULL value → **5,000**;
  unknown level → **5,000**; empty user → **5,000**.
- Env ceiling clamps a high plan down; a per-plan value below the ceiling is honoured.
- Boundary rules unchanged (sentence / word / under-limit) when driven per-plan;
  admin keeps materially more text than L1 for the same article.
- Notice by plan (entry → upsell naming 15,000; higher → limit only; no `$`).
- Audio follows text: the full-article text fed to TTS equals the plan-truncated text.
- **H:** a 15,000-char article → `polly_tts_service /synthesize` splits into
  multiple ≤2,000-char chunks and joins them into **one** deliverable (stub
  voice service; asserts in-order concatenation and that no chunk exceeds 2,000).

Other suites:

- `tests/test_local193_article_truncation.py` — updated **T8**: the old
  regression guard asserted `clean_text_for_polly` caps at ~5,050; it now asserts
  the cap is **gone** and that display + audio share one truncation. 30 tests pass.
- `tests/billing_dry_run/test_truncation.py` — unchanged, still green (uses the
  backward-compatible `truncate_article_text(text, tier)`).
- `tests/service_layer_dry_run/test_truncation_e2e.py` — rewritten to the D613
  plan model (device rows l1/l3/admin); **skips** when the levels schema /
  `article_char_limit` column is absent (LEAD applies migrations).

**Result:** `test_local708 + test_local193 + billing_dry_run/test_truncation +
test_truncation_e2e` → **54 passed, 5 skipped** (the 5 skips are the e2e tests on
the local `:5433` snapshot, which predates the D613 levels model).
`test_local69` / `test_local323` TTS-metering tests pass unchanged.
(`test_local373` has 9 failures that are **pre-existing on the clean base** —
unrelated HTML paragraph-regex extraction — verified via `git stash`.)

## Live test (own containers only — never `-p audioura`, no `audioura-*` renamed)

Ran one real Administrator article end-to-end through the **real** code
(`article_truncation.truncate_for_user` → `news_processor_service.clean_text_for_polly`
→ `polly_tts_service /synthesize`) routed to the **free host Kokoro at :5181**
(`TTS_ENGINE=kokoro`, no Polly). Plan state came from an **ephemeral own postgres**
(`local708-pg` on :5480, removed afterwards) with migration 039 applied and an
`admin` device seeded. The 14 shared `audioura-*` containers were left running
untouched.

| metric | value |
|--------|-------|
| admin plan `article_char_limit` resolved | **15,000** |
| source article | 51,078 chars |
| delivered (plan-truncated) text | 14,939 chars (sentence_boundary) |
| **characters voiced** (full-article audio) | **14,903** (old cap was 5,000) |
| TTS engine / cost | kokoro / **$0.00** |
| **MP3 length** | **5,516,013 bytes**, **919.2 s (~15.3 min)** |
| MP3 integrity | `ffprobe`: one `mp3` stream (index 0); `ffmpeg` full decode end-to-end OK — one continuous file, not byte-concatenated fragments |

This demonstrates the Administrator plan now hears ~5 pages as a single
continuous MP3, versus the old 5,000-char (~1.5 page) hard cap.

## Files

- `migration/sql/039_article_char_limit.sql` (new)
- `article_truncation.py` (rewritten — per-plan resolution + env ceiling)
- `news_processor_service.py` (removed audio 5,000 cap; audio voices plan-truncated text)
- `tests/test_local708_article_length_per_plan.py` (new)
- `tests/test_local193_article_truncation.py` (T8 updated)
- `tests/service_layer_dry_run/test_truncation_e2e.py` (rewritten to D613 plan model)

## Process notes

- No edits to DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev`.
- **LEAD applies migrations** (039).
- Branched from `subscribed` HEAD (`f2e16ba3`);
  `git merge-base --is-ancestor f2e16ba3 HEAD` exits 0.


---

# 708B — Tell the listener a better plan gives longer articles (listening + translation)

**Design of record:** D670 **addendum** + **addendum 2** (Michael, 2026-10-18).

Michael: *"User needs to know that if he would have a better plan, he would've
had longer articles listened to and translated."* and (addendum 2) the **spoken**
notice must **NAME the plans**, not say "a larger plan".

## What changed

The truncation notice is no longer a character count. A shortened article now
tells the listener which plan they are on, how long it was cut to **in pages**
(~3,000 chars ≈ 1 page), **which plans give longer articles — by NAME and page
length** — and ends with a **"See plans"** marker the app turns into a button to
Your plan. The top plans get length-only ("the maximum"). The same notice rides
a **translated** article ("listened to and translated"), and a shortened
article's **audio** ends with one spoken sentence that **names** the larger
plans. Nothing is added when the article fits. No price figure anywhere (D58 —
the plan *name* "$10 Pack" is allowed; a price *figure* is not).

### 1. `article_truncation.py` — notices rebuilt around plan data

- **Plan metadata.** `_PLAN_META_FALLBACK` holds each D613 plan's display name
  (migration 016: Introduction / Free / $10 Pack / Curator / Administrator /
  Tester) and `article_char_limit` (migration 039). `_load_plan_meta()` reads
  the **live `plans` table** (`display_name`, `article_char_limit`) so an
  operator's SQL edit flows straight into the notice; it falls back to the
  constants on any DB error. **Verified live** by renaming `l3` in the DB and
  seeing the on-screen notice change.
- **Pages, not characters.** `_pages_for_limit()` maps 5,000 → "about 1½ pages"
  / "about one and a half pages" (spoken), 10,000 → "about 3 pages" / "three",
  15,000 → "about 5 pages" / "five". Hidden plans (admin, tester) are never
  *named* in an upsell — they only ever appear as "the maximum".
- **On-screen notice** `_build_text_notice(level, meta, ceiling, translated)`:
  entry/mid plans name the current plan + the larger plans + their page lengths
  + `See plans`; top plans get "Shortened to about 5 pages, the maximum." with
  no button. `translated=True` swaps in the "listened to and translated"
  wording.
- **Spoken notice** `_build_spoken_notice(...)` (D670 addendum 2): one sentence
  that names the plans as spoken words ("$10 Pack" → "ten-dollar Pack"). For l1
  it reproduces Michael's example **verbatim**: *"This article was shortened to
  about one and a half pages on your Introduction plan. The ten-dollar Pack
  plays articles up to about three pages, and the Curator plan up to five."* Top
  plans: *"This article was shortened to about five pages, the maximum."*
- **Public helpers** for the two services: `build_text_notice_for_user`,
  `build_spoken_notice_for_user`, `build_spoken_notice(level)`,
  `truncate_for_user_with_notice(text, user_id, notice)`. `truncate_for_user`
  now resolves the **level** (not just the limit), builds the rich notice from
  it, and takes a `translated` flag.
- Legacy symbols (`_FREE_NOTICE_A/_B`, `_SUBSCRIBED_NOTICE_A/_B`, `_get_notice`,
  `_notice_for_limit`) are retained for the legacy tier path and the old tests;
  `_notice_for_limit` now emits the page-based wording too.

### 2. `news_processor_service.py` — English audio names the plans

The full-article audio (`audio-99`) is still voiced from the plan-truncated
`display_text` (708). **Only when `was_truncated`**, the spoken notice
(`build_spoken_notice_for_user(secret_id, translated=False)`) is appended to the
voiced text. Nothing is added for an article that fits.

### 3. `translation-service/translation_service.py` — translated notice + audio

`translate_article(..., user_id)` threads the requesting listener's `user_id`
(already present on the `/translate-with-audio` endpoint) into
`_create_english_structure_zip(..., user_id)`. There the **already-translated**
full article is truncated to the listener's plan with
`truncate_for_user_with_notice`, carrying a notice that is **built in English
("listened to and translated") then translated into the target language** via
the service's own `translate_text` (English fallback if the app isn't localised
/ translation fails). The full-article audio ends with the **translated spoken
notice**. Fail-open: any error delivers the untranslated-length text with no
notice.

### 4. Build plumbing (so the import actually resolves)

`article_truncation` + `subscription_levels` are now **copied into the image**
of the two services that call them:

- `Dockerfile.news-processor` (build context = repo root): added
  `COPY article_truncation.py .` and `COPY subscription_levels.py .` (these were
  **not** copied before — a latent gap from 708 on the explicit-list Mac
  Dockerfiles).
- `translation-service/Dockerfile` (build context = `./translation-service`,
  which cannot reach repo-root files): added copies of both modules **into
  `translation-service/`** and to the Dockerfile `COPY` list — the same
  convention the service already uses for `cost_meter.py`. The two
  `article_truncation.py` copies are byte-identical and **must be kept in sync**.

## Tests

- `tests/test_local708b_plan_notice.py` (**16**): on-screen notice per plan
  (l1 names $10 Pack + Curator lengths; l3 names Curator only; l4/admin
  length-only "the maximum", no See plans); no price *figure* anywhere; a fitting
  article gets no notice; translated wording present; spoken notice names the
  larger plans and page lengths (l1 asserts the **exact** D670 addendum-2
  sentence); translated spoken wording; the "only when truncated" audio gate.
- `tests/test_local708b_translated_article.py` (**4**): drives
  `TranslationService._create_english_structure_zip` with `translate_text` /
  `generate_audio` stubbed — asserts the translated notice **and** `See plans`
  reach the HTML `full_text`, the translated **spoken** notice reaches the
  full-article audio, the top plan says "the maximum", a fitting article adds
  nothing, and an `en` target is not re-translated.
- Updated old-wording assertions to the D670 page wording in
  `tests/test_local708_article_length_per_plan.py` (`TestNoticeByPlan`, the admin
  boundary marker), `tests/test_local193_article_truncation.py` (T2), and
  `tests/billing_dry_run/test_truncation.py` (free tier now asserts
  "See plans" + "page", not "Subscribe"/char counts).

**Result:** `test_local708 + test_local708b_plan_notice +
test_local708b_translated_article + test_local193 + billing_dry_run/test_truncation
+ service_layer_dry_run/test_truncation_e2e` → **74 passed, 5 skipped** (same 5
e2e skips as 708 — they need the live levels schema). TTS-metering suites
(`test_local69_news_metering`, `test_local323_tts_metering`) → **97 passed**, no
regression.

## Live verification (own containers only)

Ran the **real** `article_truncation` path against an **ephemeral own postgres**
(`local708b-pg` on :5481, removed afterwards; the 14 shared `audioura-*`
containers were left untouched) seeded with the migration-016 plan names and
migration-039 limits and `device_entitlement` rows `dev-l1` / `dev-l3` /
`dev-admin`.

| device | resolved limit | delivered | on-screen notice | spoken notice |
|--------|---------------:|----------:|------------------|---------------|
| dev-l1 | 5,000 | 4,986 | "Shortened to about 1½ pages on the Introduction plan. The $10 Pack plays articles up to about 3 pages, Curator up to 5 — See plans" | matches the D670 addendum-2 example verbatim |
| dev-l3 | 10,000 | 9,933 | "Shortened to about 3 pages on the $10 Pack plan. The Curator plays articles up to about 5 pages — See plans" | "…about three pages on your ten-dollar Pack plan. The Curator plays articles up to about five pages." |
| dev-admin | 15,000 | 14,948 | "Shortened to about 5 pages, the maximum." | "This article was shortened to about five pages, the maximum." |

Translated variants used the "listened to and translated" wording; a short
article produced `truncated=False` and **no** notice. Renaming `l3` in the DB
changed the on-screen notice, proving `_load_plan_meta` reads the **live** table.

## Files (708B)

- `article_truncation.py` (notices rebuilt; new public helpers) — and its
  in-sync copy `translation-service/article_truncation.py`
- `subscription_levels.py` copy added at `translation-service/subscription_levels.py`
- `news_processor_service.py` (spoken notice appended to audio-99 when truncated)
- `translation-service/translation_service.py` (user_id threaded; translated
  notice + translated spoken notice)
- `translation-service/Dockerfile`, `Dockerfile.news-processor` (COPY the two
  shared modules)
- `tests/test_local708b_plan_notice.py` (new), `tests/test_local708b_translated_article.py` (new)
- `tests/test_local708_article_length_per_plan.py`, `tests/test_local193_article_truncation.py`,
  `tests/billing_dry_run/test_truncation.py` (assertions updated to D670 wording)

## Process notes (708B)

- No edits to DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev`.
- **LEAD applies migrations** (039 already from 708; 708B adds no migration).
- Continued on `LOCAL-708-article-length-per-plan`; `git merge origin/subscribed`
  was a no-op (already up to date); base `f2e16ba3` is an ancestor of HEAD.
