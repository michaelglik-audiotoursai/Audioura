# SUBMISSION_LOCAL-366.md

## Summary

Exhibition checklist retrieval from a venue's own structured data is now proven
end-to-end for the **Art Institute of Chicago** via its public REST API.
The MFA Boston case remains unsolvable without a headless browser.

---

## Route 1: Venue's Own Structured Data (MFA Boston)

### drupal-settings-json Blob

The MFA exhibition page (`https://www.mfa.org/exhibition/picasso-miro-dali-unbound`)
contains a `data-drupal-selector="drupal-settings-json"` script tag. Parsed contents:

```
Top-level keys: path, pluralDelimiter, suppressDeprecationErrors, ajaxPageState,
                ajaxTrustedUrl, gtag, gtm, ajaxLoader, colorbox, field_group,
                views, tnewCookieName, user

views.ajaxViews contains ONE view:
  view_name: "banner"
  view_display_id: "block_1"
  view_args: "167181"
  view_path: "/node/167181"
```

**Finding:** The Drupal Views configuration only defines a banner image view.
There is no artwork/collections/exhibition-objects view. No exhibition checklist
data is embedded in the server-rendered HTML.

### `/api/` Reference

The only `/api/` reference in the page is `/api/player.js` — a Tessitura/TNEW
ticketing system player. Not a collections API.

### JSON:API Endpoints

| Endpoint | Result |
|----------|--------|
| `/jsonapi` | 404 |
| `/jsonapi/node/exhibition` | 404 |
| `/api/` | 404 |
| `/node/167181?_format=json` | "A route that returns a rendered array...only supports the HTML format." |

JSON:API module is not enabled on this Drupal instance.

### collections.mfa.org

| Path | Result |
|------|--------|
| `/` | 403 (awselb/2.0) |
| `/objects` | 403 |
| `/search` | 403 |
| `/api` | 403 |

Behind an ELB that blocks all requests without specific headers/auth.

### `/collections/object/*` (Collection Object Pages)

Returns `403 cf-mitigated: challenge` with Cloudflare bot protection.
These pages exist but are gated behind a JavaScript challenge.

### Page Content Analysis

The exhibition page (87KB, HTTP 200) contains:
- 1 image (repeated 4x) with alt text "Abstract black-line drawing..."
- 1 artwork credit: "Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers)"
- Exhibition description prose (2 paragraphs)
- An Instagram embed reel
- Sponsor acknowledgments
- **Zero** `/collections/object` links
- **Zero** JSON-LD blocks
- **Zero** artwork entity UUIDs

**Conclusion for Route 1 (MFA):** Dead end. The exhibition page serves only
marketing prose. Artwork data is loaded client-side by JavaScript from an
undiscoverable endpoint (likely behind the Cloudflare challenge).

---

## Route 2: Collection Search Filtered by Exhibition (MFA)

The MFA's `/collections` page is also a Drupal node (node/23179) with a single
form input (`name="search"`, type webform). The drupal-settings-json on this
page also contains only a banner view.

There is no exhibition facet parameter observable in the URL structure. The
actual search is JavaScript-rendered via an undiscoverable backend.

**Conclusion for Route 2:** Dead end. No URL-addressable search endpoint with
an exhibition facet exists on mfa.org.

---

## Route 3: Second Venue with Static Checklists

### Venues Tried

| Venue | Result |
|-------|--------|
| MoMA | 403 Cloudflare challenge |
| Art Institute of Chicago (artic.edu) | 403 Cloudflare challenge |
| National Gallery of Art | 403 Cloudflare challenge |
| Tate | 200, but exhibition pages have minimal artwork links |
| Yale Art Gallery | 200, but exhibition pages don't list individual works |
| Philadelphia Museum | 200, JS-rendered search |
| **api.artic.edu (AIC public API)** | ✅ 200, CC0-licensed, full artwork data |

### Art Institute of Chicago — Public REST API

The AIC's website (artic.edu) is behind Cloudflare, but their **data API**
at `api.artic.edu` is completely open, CC0-licensed, and returns structured
exhibition checklists.

**API Documentation:** https://api.artic.edu/docs

**Endpoints used:**
```
GET https://api.artic.edu/api/v1/exhibitions/search?q={name}&fields=id,title,status,artwork_ids,artwork_titles,aic_start_at,aic_end_at,web_url&limit=10
GET https://api.artic.edu/api/v1/artworks?ids={comma-separated}&fields=id,title,artist_title,date_display
```

### Exhibition Proven: "Beyond Form: Abstraction at Midcentury"

- **Exhibition ID:** 10694
- **URL:** https://www.artic.edu/exhibitions/10694/beyond-form-abstraction-at-midcentury
- **Status:** Confirmed (on view 2026-06-27 through 2026-10-19)
- **API source:** `https://api.artic.edu/api/v1/exhibitions/10694`
- **Artwork count:** 71

### Verbatim Extracted Titles (from API, all 71)

```
 1. Hyderabad — Rasheed Araeen, 1962
 2. Untitled — Michel Cardena, 1969
 3. Plane Tree Reversal — Ruth Asawa, 1965
 4. Gray Interior (aka Gray Morning) — Romare Howard Bearden, 1969
 5. Cyclopean — Byron Browne, 1949
 6. Untitled — Wifredo Arcay, 1953
 7. Litho #2 (Waves #2) — Willem de Kooning, 1960
 8. Moscovite — Dorothy Dehner, 1950
 9. Untitled — Beauford Delaney, 1961
10. Untitled (Berkeley) — Richard Diebenkorn, 1955
11. Grate — Sari Dienes, 1953/55
12. Contemporary Ikon — Jimmy Ernst, 1954
13. Untitled, from Squares (Cuadrados) — Manuel Espinosa, c. 1970
14. Untitled — Claire Falkenstein, 1953
15. Wide to the Wind — Perle Fine, 1955
16. Untitled — Lucio Fontana, c. 1964
17. Black and Green — Sam Francis, 1953
18. Shore Figure — Helen Frankenthaler, 1959
19. Untitled — Gego (Gertrud Goldschmidt), 1968
20. Abstraction — Sam Gilliam, 1970
21. Untitled — Arshile Gorky, 1943
22. The Vendor #3 — Grace Hartigan, 1956
23. Abstraction — Stanley William Hayter, 1960
24. Forms in a Landscape — Richard Hunt, 1962
25. Untitled, from Resist — Luchita Hurtado, 1958
26. Study for "Cité": Brushstrokes Cut into Twenty Squares and Arranged by Chance — Ellsworth Kelly, 1951
27. Chicago — Franz Kline, 1959
28. Black and White — Lee Krasner, 1953
29. Sun Spot — Yayoi Kusama, 1953
30. Untitled — Jacqueline Lamba, 1943
31. Abstract Composition — Conrad Marca-Relli, 1956
32. Untitled — Roberto Matta, n.d.
33. Zen — George Joji Miyasaki, 1958
34. Untitled — Nasreen Mohamedi, late 1960s
35. The Mediterranean Sky — Robert Motherwell, 1961
36. Gea — Barnett Newman, 1944–45
37. Untitled — Tetsuo Ochikubo, 1961
38. Metaesquema, No. 244 — Hélio Oiticica, 1957
39. 5907 — Fayga Ostrower, 1959
40. TV Dream/Dream TV — Nam June Paik, 1963
41. Untitled — Lygia Pape, 1959
42. Fire Painting — Otto Piene, 1967
43. Untitled — Jackson Pollock, 1944
44. Sonata — Richard Pousette-Dart, 1940s
45. Soot Series #1 — Deborah Remington, 1963
46. Untitled Sketchbook [Working Study for Soot Series] — Deborah Remington, 1969
47. Sketchbook — Deborah Remington, 1965-70
48. Untitled — Mark Rothko, c. 1944
49. #X66 — Anne Ryan, c. 1950
50. Untitled — Mira Schendel, 1964
51. Untitled — Mira Schendel, 1964
52. Untitled — Mira Schendel, 1964
53. Untitled — Mira Schendel, 1964
54. Untitled — Mira Schendel, 1964
55. Untitled — Mira Schendel, 1964
56. Untitled — Shinoda Toko, 1965
57. David Smith — Untitled, 1955
58. Double Concentric Squares — Frank Stella, n.d.
59. Untitled — Hedda Sterne, c. 1950
60. Untitled — Myron Stedman Stout, c. 1954
61. Thar — Yves Tanguy, 1952
62. Untitled — Tanaka Atsuko, 1963
63. Red Circle — Lenore Tawney, 1964
64. Sperlonga — Cy Twombly, 1959
65. Esteban Vicente — Collage No. 7, 1952
66. Les Jardins No.2 — Maria Helena Vieira da Silva, 1966
67. Work — Kanayama Akira, 1952
68. Untitled — Pennerton West, n.d.
69. Untitled — Hannah Wilke, 1960s
70. Untitled — Jirô Yoshihara, 1965
71. Mondrian I — James Bishop, n.d.
```

---

## Implementation

### Code Changes

**`exhibition_checklist.py`** — Added `_try_aic_api()` function (≈130 lines):
- Detects AIC venue via name matching ("art institute of chicago", "artic.edu")
- Queries `/api/v1/exhibitions/search` with fuzzy title matching
- Fetches artwork details from `/api/v1/artworks?ids=...`
- Returns `ExhibitionChecklistResult` with `page_shape='api_structured'`
- Called at the top of `find_exhibition_checklist()` before HTML scraping path
- Returns `None` for non-AIC venues (zero performance impact on existing path)

### Test File

**`tests/test_local366_aic_api_checklist.py`** — 19 tests:
- `TestAICAPIDetection` (5 tests): venue name matching, non-AIC skip
- `TestAICAPIArtworkExtraction` (2 tests): title/artist extraction from fixtures
- `TestAICAPIClosedExhibition` (1 test): closed show detection
- `TestAICAPITitleMatching` (3 tests): fuzzy matching, threshold rejection
- `TestMFAExhibitionPage` (4 tests): MFA page analysis proving prose-only
- `TestFindExhibitionChecklistIntegration` (2 tests): routing logic
- `TestUnscopedUnchanged` (2 tests): plain venues not affected

### Fixtures (from live fetches 2026-08-10)

- `tests/fixtures/aic_exhibition_10694.json` — AIC API exhibition response
- `tests/fixtures/aic_artworks_10694.json` — 71 artworks with artist names
- `tests/fixtures/mfa_picasso_exhibition.html` — 87KB MFA page (prose-only)

---

## Red/Green Evidence

### RED (production code disabled):
```
$ python3 -c "..." # Disable _try_aic_api → always returns None
$ python3 -m pytest tests/test_local366_aic_api_checklist.py::TestFindExhibitionChecklistIntegration::test_aic_venue_uses_api_path -x --tb=line

FAILED tests/test_local366_aic_api_checklist.py::TestFindExhibitionChecklistIntegration::test_aic_venue_uses_api_path
  AssertionError: assert 'fallback' == 'checklist'
```

### GREEN (production code restored):
```
$ python3 -m pytest tests/test_local366_aic_api_checklist.py -v
======================== 19 passed, 1 warning in 0.16s =========================
```

---

## Acceptance Checklist

| Criterion | Status |
|-----------|--------|
| Works retrieved from venue for real exhibition | ✅ 71 works from AIC API |
| Verbatim titles pasted | ✅ All 71 above |
| URL source identified | ✅ `https://api.artic.edu/api/v1/exhibitions/10694` |
| MFA routes tried and documented | ✅ Routes 1, 2, 3 all documented |
| Unscoped venues unchanged | ✅ Tests pass |
| Museum bounds hold (75.0/81.2) | ✅ TestMuseumScoreBounds + TestMuseumBoundsProperty pass |
| Tests against real fixtures (not hand-written) | ✅ All fixtures from live fetches |
| Red/green proven | ✅ Shown above |

---

## Limitations

1. **MFA Boston remains unsolved.** The exhibition page is marketing prose
   rendered server-side, with artwork data loaded by JavaScript from an
   undiscoverable Cloudflare-protected endpoint. A headless browser
   (Playwright/Selenium) would be required to obtain the checklist. This
   is an infrastructure decision.

2. **AIC API coverage is venue-specific.** The `_try_aic_api` function only
   fires for the Art Institute of Chicago. Other museums that expose similar
   APIs (Met, Smithsonian) would need additional integrations, but the pattern
   is now established and extensible.

3. **Not all AIC exhibitions have `artwork_ids` populated.** Upcoming shows
   (e.g., Mary Cassatt: After Impressionism, opening Sep 2026) have empty
   artwork lists until the curator finalizes the checklist in the CMS.

4. **Many major museum sites (MoMA, Met, NGA, AIC main site) are behind
   Cloudflare challenges.** Static HTTP retrieval from these sites returns 403.
   Only api.artic.edu (a separate subdomain, deliberately public) is accessible.
