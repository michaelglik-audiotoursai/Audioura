# Lighthouse results (mobile) — LOCAL-812 / LOCAL-812B

Run with `lighthouse@12` (headless Chrome), form-factor mobile, against
`python3 -m http.server`. Targets: SEO ≥ 95, Accessibility ≥ 95,
Performance ≥ 90.

Re-run for **LOCAL-812B** after the phone-overflow and honest-duration fixes.

| Page | Performance | Accessibility | SEO | Best Practices |
|---|---|---|---|---|
| Tour page — /tours/paris/louvre-museum-audio-tour/ | 100 | 100 | 100 | 96 |
| City hub — /tours/paris/ | 100 | 98 | 100 | 96 |
| Pricing — /pricing/ | 100 | 98 | 100 | 96 |

All three pages meet or exceed every target. Full reports:
`docs/lighthouse/*.report.html`.

## Phone-width overflow check (LOCAL-812B)

`build/check_overflow.js` loads each of the three pages in headless Chrome at
**360, 390 and 430 CSS px** and asserts
`document.documentElement.scrollWidth <= window.innerWidth` (and that no element
extends past the right edge). All 9 page×width combinations pass — see
`docs/overflow-check.json` (`failures: 0`). Phone-width (390 CSS px) screenshots:
`docs/tour-page-phone.png`, `docs/pricing-page-phone.png`.
