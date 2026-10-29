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


---

## 812B — bounce fixes: phone overflow + honest durations

LEAD review of `docs/tour-page-phone.png` (Louvre) found two problems. Both are
fixed; the whole site was regenerated and re-checked. Paid-API spend this round:
**$0** (no Serper or other metered calls).

### 1. Horizontal overflow at phone width — fixed

The H1, intro, sample box, stop titles (long French artwork names) and FAQ ran
past the right edge. Fixed at the source in `assets/css/site.css`:

- **Fluid type** — `h1/h2/h3` now use `clamp()` (e.g. `h1: clamp(1.5rem, 7vw,
  2rem)`) so headings shrink on narrow phones instead of forcing width. Desktop
  bump is also `clamp()`-capped.
- **Wrapping** — `overflow-wrap: anywhere` on text elements, plus
  `word-break: break-word` on titles/paragraphs so an unbreakable token (like
  "La Décollation de saint Jean-Baptiste") wraps rather than overflowing.
- **No fixed-width elements** — `html, body { max-width: 100% }`,
  `max-width: 100%` on `img/audio/video/iframe/svg/table`, and `box-sizing:
  border-box` (already global). Short price values in the pricing table use
  `white-space: nowrap` so "$2.99" is never split.
- I deliberately did **not** use `overflow-x: hidden` — that would only *mask*
  overflow and make the check below pass trivially. The layout is fixed, not
  clipped.

**Check (`build/check_overflow.js`, headless Chrome):** each of the 3 pages is
loaded at **360 / 390 / 430 CSS px** and asserts
`document.documentElement.scrollWidth <= window.innerWidth` (and that no element
extends past the right edge). **All 9 page×width combinations pass** —
`scrollWidth == innerWidth` everywhere, `failures: 0`. Evidence:
`docs/overflow-check.json`. New 390 px screenshots: `docs/tour-page-phone.png`,
`docs/pricing-page-phone.png`.

### 2. Honest duration — fixed

The pages invented tour durations ("5 masterpieces in 60 minutes", "~60 min").
The real narration is far shorter. `build/extract_tours.py` now **measures** the
listening time with `ffprobe`: it sums every `audio_*.mp3` inside each tour's
catalog ZIP and rounds to the nearest minute → `listen_min` (the old hand-written
`duration_min` is gone). Measured values:

| Tour | Real listening (ffprobe) |
|---|---|
| Montmartre (844) | 12 min |
| **Louvre (845)** | **10 min** |
| Colosseum & Forum (846) | 12 min |
| British Museum (848) | 11 min |
| Met (850) | 12 min |
| Gothic Quarter (852) | 10 min |
| Gaudí (853) | 11 min |
| Sultanahmet (856) | 11 min |
| Prague Old Town (858) | 11 min |
| Uffizi (859) | 10 min |

The generator now shows **"≈ 10 min listening"** from the real audio and, for
walking tours, a **separate** **"≈ X km walk"** figure — listening time and
walking distance are different things and are never conflated. The intro, meta
description and FAQ say so explicitly (e.g. Louvre: *"The narration runs about 10
minutes of listening"*; Montmartre: *"That's about 12 minutes of listening; the
walk between the 5 stops is about 1.2 km"*). Invented durations were removed from
H1/title/meta — the Louvre H1 is now *"Louvre Museum audio tour — 5 masterpieces,
narrated"* and the British Museum's drops *"in an hour"*. A grep for the old
duration strings (`in 60 minutes`, `in an hour`, `~60 min`, `takes about N
minutes`, …) across `tours/` and `pricing/` returns **nothing**.

### Re-checks

- **Lighthouse (mobile, `lighthouse@12`)** re-run on the same 3 pages — unchanged
  and still above target: Louvre **100/100/100/96**, Paris hub
  **100/98/100/96**, Pricing **100/98/100/96** (Perf / A11y / SEO / Best
  Practices). Reports: `docs/lighthouse/*.report.html`; summary
  `docs/LIGHTHOUSE.md`.
- **JSON-LD** — `build/validate_jsonld.py`: 20 pages / 49 blocks, all valid.
- **Meta descriptions** — all 10 remain 138–160 chars.

### Files changed (812B)
- `website/seo/assets/css/site.css` — overflow/fluid-type fixes.
- `website/seo/build/extract_tours.py` — ffprobe `listen_min`; invented durations
  removed from `TOUR_META`.
- `website/seo/build/generate_site.py`, `build/faqs.py` — use `listen_min` +
  separate walk distance; honest H1/meta/intro/FAQ.
- `website/seo/build/check_overflow.js` — the new scrollWidth check (added).
- `website/seo/build/tours_data.json` — regenerated (`listen_min`).
- `website/seo/tours/**`, `pricing/index.html`, `sitemap.xml` region —
  regenerated HTML.
- `website/seo/docs/` — new `overflow-check.json`, refreshed phone screenshots,
  re-run Lighthouse reports, updated `LIGHTHOUSE.md`.

Everything stays under `website/seo/` (+ this file). Still staged by path only —
no `git add -A`; no edits to the protected files. Catalog ZIPs remain
uncommitted.
