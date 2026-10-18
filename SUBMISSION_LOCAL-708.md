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
