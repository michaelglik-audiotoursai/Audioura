# Audioura SEO tour pages (`website/seo/`) — LOCAL-812

A **staged, static** SEO site for audioura.com: one page per catalog tour, a
city hub per destination, a tours index, and a pricing page. Pure HTML + one CSS
file + one small lazy-loaded JS map. No framework, no build step for the reader.

> **Nothing here is published.** This directory lives in the repo for LEAD to
> preview and Michael to approve. The live site is a Cloudflare assets-only
> Worker/Pages project — this task does **not** deploy, touch DNS, or call
> Cloudflare. Store links and a few other items are placeholders until Michael
> provides the live values (see "Before it goes live").

## What's here

```
website/seo/
├── tours/
│   ├── index.html                        # all tours, grouped by city
│   ├── <city>/index.html                 # 8 city hubs
│   └── <city>/<slug>/index.html          # 10 tour pages
├── pricing/index.html                    # passes + 5-tour pack (D734)
├── sitemap.xml                           # all 20 public URLs
├── robots.txt                            # allow all + sitemap
├── assets/
│   ├── css/site.css                      # shared styles (mobile-first, a11y)
│   ├── js/map.js                         # lazy Leaflet+OSM route map
│   ├── audio/<slug>-sample.mp3           # 45-second samples (264 KB each)
│   └── og/<slug>.png, default.png        # 1200×630 Open Graph cards
├── KEYWORDS.md                           # Serper keyword research per tour
├── docs/                                 # Lighthouse reports + phone screenshots
└── build/                                # generators (not part of the site)
```

### Pages
- **10 tour pages** — `/tours/<city>/<slug>/`. Natural H1, 120–160-char meta
  description, intro, the 5 stops each with a 1–2 sentence **rewritten** teaser
  (never the full narration), duration/distance, a lazy route map, a 45-second
  audio sample (`preload="none"`), "Listen on the app" buttons, and a 3-question
  FAQ drawn from real "People also ask" questions.
- **8 city hubs** — Paris, Rome, London, New York, Barcelona, Istanbul, Prague,
  Florence — plus the `/tours/` index.
- **Pricing** — the same two-choice framing as the app: a time-limited pass
  ($2.99/day · $4.99/week · $9.99/month · $79.99/year) or a 5-tour pack ($10, no
  time limit).

### Structured data (JSON-LD)
Each tour page carries **TouristTrip** (with an itinerary of **TouristAttraction**
items with geo coordinates), an **AudioObject** for the sample, a
**BreadcrumbList**, and an **FAQPage**. Hubs/index carry **ItemList**; pricing
carries **Product/Offer**. All 49 blocks validate offline
(`build/validate_jsonld.py`).

## Preview locally

```bash
cd website/seo
python3 -m http.server 8000
# then open http://localhost:8000/tours/
```

Browse `/tours/`, a city hub (`/tours/paris/`), a tour page
(`/tours/paris/louvre-museum-audio-tour/`), and `/pricing/`. The route map lazy-
loads Leaflet from unpkg (needs network); with JS off, the stop list still
describes the route.

## Re-generate the site

The HTML is generated from the catalog, so edits should be made to the builders,
not the HTML. The ZIPs are **not** committed; regeneration needs them at
`~/Audioura/catalog/export`.

```bash
cd website/seo/build
python3 extract_tours.py        # ZIPs → tours_data.json (titles, stops, geo, teaser source)
python3 make_og_cards.py        # → assets/og/*.png
# audio samples (ffmpeg): 45 s, mono, 48 kbps, from each tour's stop 1
python3 generate_site.py        # → all HTML + sitemap.xml + robots.txt
python3 validate_jsonld.py      # offline JSON-LD check
```

Keyword research (optional; costs ~$0.015 of Serper credit, routed through the
metered door `serper_meter`):

```bash
cd website/seo/build && python3 keyword_research.py   # → KEYWORDS.md + keywords.json
```

## Checks

- **Lighthouse (mobile)** on 3 pages — all meet the targets (SEO ≥ 95,
  Accessibility ≥ 95, Performance ≥ 90). See `docs/LIGHTHOUSE.md` and
  `docs/lighthouse/*.report.html`.
- **Phone screenshots** at 390 CSS px — `docs/tour-page-phone.png`,
  `docs/pricing-page-phone.png`.

## Before it goes live (placeholders to fill)

- **Store URLs** — App Store and Google Play buttons currently link to `#` and
  show a "placeholders until the apps are published" note. Set the real URLs in
  `build/generate_site.py` (`APP_STORE_URL`, `GOOGLE_PLAY_URL`) and re-generate.
- **hreflang** — English only for now; add alternates when localized pages exist.
- **Logo / screenshots** — the pages use a text wordmark and generated OG cards
  (no stock photos); swap in real brand art when available.

## Deploy later (steps only — not done by this task)

The home page and the `/t/<CODE>` share-links already live on audioura.com via
Cloudflare. These SEO pages are additional static assets at the site root:

1. Copy the **contents** of `website/seo/` to the site root of the Cloudflare
   project so paths resolve as `/tours/…`, `/pricing/`, `/assets/…`,
   `/sitemap.xml`, `/robots.txt`. Do not nest under a subfolder. (They slot in
   alongside the existing `/t/`, `/.well-known/`, `_headers`, `_redirects`.)
2. Confirm the origin is `https://www.audioura.com` — canonical URLs, OG tags
   and the sitemap all use that host. If the canonical host is the apex
   `audioura.com` instead, set `ORIGIN` in `build/generate_site.py` and
   regenerate so canonicals match the served host exactly.
3. Deploy the Cloudflare project (push to the connected branch, or drag-and-drop
   in the dashboard → Workers & Pages → the audioura.com project → Create
   deployment).
4. Verify after deploy:
   - `https://www.audioura.com/tours/` and a tour page render.
   - `https://www.audioura.com/sitemap.xml` and `/robots.txt` are served.
   - OG cards resolve (`/assets/og/<slug>.png`) — test a link in a social
     preview / the Facebook Sharing Debugger and Twitter Card Validator.
5. Submit the sitemap in Google Search Console once the pages are live.
