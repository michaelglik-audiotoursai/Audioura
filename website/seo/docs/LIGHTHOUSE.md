# Lighthouse results (mobile) — LOCAL-812

Run with `lighthouse@12` (headless Chrome), form-factor mobile, against `python3 -m http.server`. Targets: SEO ≥ 95, Accessibility ≥ 95, Performance ≥ 90.

| Page | Performance | Accessibility | SEO | Best Practices |
|---|---|---|---|---|
| Tour page — /tours/paris/louvre-museum-audio-tour/ | 100 | 100 | 100 | 96 |
| City hub — /tours/paris/ | 100 | 98 | 100 | 96 |
| Pricing — /pricing/ | 100 | 98 | 100 | 96 |

All three pages meet or exceed every target. Full reports: `docs/lighthouse/*.report.html`.

Phone-width (390 CSS px) screenshots: `docs/tour-page-phone.png`, `docs/pricing-page-phone.png`.
