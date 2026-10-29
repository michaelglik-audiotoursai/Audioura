# SUBMISSION — LOCAL-812: SEO tour pages for audioura.com (STAGED)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-812-seo-pages`
**Base:** `subscribed` @ `e51d089f` (`git merge-base --is-ancestor e51d089f HEAD` → exit 0)

> **Staged, not published.** Everything lives under `website/seo/`. This task
> does not deploy, change DNS, or call Cloudflare. LEAD previews; Michael
> approves and publishes later.

## What was built

A static, framework-free SEO site for the 10 kept catalog tours
(`~/Audioura/catalog/export/manifest.json`, track `subscribed`):

| Area | Count | Path |
|---|---|---|
| Tour pages | 10 | `/tours/<city>/<slug>/` |
| City hubs | 8 | `/tours/<city>/` (Paris, Rome, London, New York, Barcelona, Istanbul, Prague, Florence) |
| Tours index | 1 | `/tours/` |
| Pricing | 1 | `/pricing/` |
| Sitemap / robots | — | `/sitemap.xml`, `/robots.txt` |

20 HTML pages total. Tour-content and stop titles were read from the ZIPs in
`~/Audioura/catalog/export`; **the ZIPs are not committed**.

### Each tour page has
- A natural **H1** (e.g. "Louvre Museum audio tour — 5 masterpieces in 60 minutes").
- A **120–160-char meta description** (all 10 verified in range).
- An intro paragraph, then the **5 stops** each with a 1–2 sentence **rewritten
  teaser** — the full narration is never republished.
- Duration / distance pills, a lazy **Leaflet + OpenStreetMap** route map (with
  OSM attribution, loaded only when scrolled into view), a **45-second audio
  sample** (`preload="none"`), "Listen on the app" **store buttons**
  (placeholder links), and a **3-question FAQ** from real "People also ask"
  queries.
- **JSON-LD**: `TouristTrip` (itinerary of `TouristAttraction` with geo),
  `AudioObject`, `BreadcrumbList`, `FAQPage`.
- Canonical URL, Open Graph + Twitter `summary_large_image` cards.

## Keyword research (Serper) — within cap

`build/keyword_research.py` ran **15 Serper organic-search queries** (one per
tour + 5 supplementary for tours whose first query returned no "People also
ask"). Serper bills $0.001/query → **$0.015 total**, under the **$0.20** cap.

Every call routes through **`serper_meter.serper_search`** — the one metered
door (LOCAL-707), so the spend is recorded in `paid_api_calls`. The
`tests/test_local707_serper_scan_guard.py` static guard is satisfied:
`keyword_research.py` imports `serper_meter` and never POSTs to `serper.dev`
directly. Results committed to `website/seo/KEYWORDS.md`.

## Audio samples
`ffmpeg` trims the first 45 s of each tour's stop 1, re-encoded mono 48 kbps MP3.
Each file is **264 KB** — under the **400 KB** commit threshold — so all 10 are
committed at `assets/audio/<slug>-sample.mp3` (45.0 s, verified with `ffprobe`).

## Open Graph cards
`build/make_og_cards.py` renders a 1200×630 PNG per tour from a branded template
(deep indigo gradient, amber wordmark + soundwave motif) using PIL — **no stock
photos**. 34–48 KB each.

## Checks

### Lighthouse (mobile, `lighthouse@12`, headless Chrome)
| Page | Perf | A11y | SEO | Best Practices |
|---|---|---|---|---|
| `/tours/paris/louvre-museum-audio-tour/` | 100 | 100 | 100 | 96 |
| `/tours/paris/` | 100 | 98 | 100 | 96 |
| `/pricing/` | 100 | 98 | 100 | 96 |

All exceed the targets (**SEO ≥ 95, Accessibility ≥ 95, Performance ≥ 90**).
Reports: `docs/lighthouse/*.report.{html,json}`; summary `docs/LIGHTHOUSE.md`.

### JSON-LD
`build/validate_jsonld.py` (offline) checked **20 pages / 49 JSON-LD blocks** —
all valid: `@context` = schema.org, correct `@type`, type-specific required
properties, plus deep checks on the TouristTrip itinerary/AudioObject, FAQPage
Q&A, BreadcrumbList items, and Product offers.

### Screenshots
`docs/tour-page-phone.png`, `docs/pricing-page-phone.png` at 390 CSS px.

## Decisions / notes
- **Pricing** reflects D734: Day $2.99 · Week $4.99 · Month $9.99 · Annual
  $79.99 · 5-tour pack $10 (no time limit). Same two-choice framing as the app
  (pass vs pack).
- **Museum tours** (Louvre, British Museum, Met, Uffizi): the 5 stops are
  artworks inside one building, so they share the venue's coordinates — the map
  centres on the museum. This is accurate, not a data error.
- **Tone / brand** follows `WEBSITE_BRIEF_audioura_com.md`: "Where stories guide
  you", consumer voice, listen-don't-look. No investor/fundraising content.
- **FAQ answers** are truthful about what Audioura is (a self-guided audio-tour
  app) and never invent third-party ticket prices or hours; venue-ticket
  questions point visitors to the official venue.
- **Placeholders** (documented in `website/seo/README.md`): store URLs (`#`),
  hreflang (English only), real logo/screenshots. English only for now.

## Files (committed)
- `website/seo/` — generated site (HTML, CSS, JS, audio, OG cards), `KEYWORDS.md`,
  `README.md`, `docs/` (Lighthouse + screenshots), and `build/` generators
  (`extract_tours.py`, `keyword_research.py`, `make_og_cards.py`,
  `generate_site.py`, `teasers.py`, `faqs.py`, `validate_jsonld.py`,
  `tours_data.json`, `keywords.json`).
- `SUBMISSION_LOCAL-812.md` (this file).

Staged `git add` by path only — no `git add -A`. The catalog ZIPs are not
committed. No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, or TRAVEL_PROJECTS.md.
