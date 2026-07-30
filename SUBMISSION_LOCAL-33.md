##### READY FOR REVIEW

## LOCAL-33: Crawl Scoping — Fix municipal-portal crawl bleed

### Problem
Palais Lascaris's `official_url` is a page on the City of Nice municipal portal
(`nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais`). The crawler
left the museum section and wandered the entire city site — sports halls, admin
tariffs, contact pages — producing garbage input to the classifier.  Only 1 stop
was deliverable.

### Root cause
The crawler constrained links to `_base_domain` only (same host), not to the
venue's own path prefix.  For portal-hosted museums, every page on the domain
passed the filter.

### Fix (3 parts)

1. **Crawl scoping** (`story_miner.py`): When `official_url` has a deep path
   (>1 segment), constrain all link-following to that path prefix.  Bare-domain
   URLs (like `maa.departement06.fr`) retain whole-site crawl.

2. **Visitor-info scoping** (`generate_tour_text.py`): Deep-path URLs only
   probe for visitor info within the venue's own section (sibling pages), never
   root-level paths that belong to the portal.  Added validity gate from
   LOCAL-32 to reject nav junk text.

3. **Richer Wikipedia extraction** (`story_miner.py` Pattern 7): When the
   venue's own site section is thin, named instruments/artworks with maker
   attribution are extracted from Wikipedia (EN+FR) using a new regex pattern.
   This leverages Wikipedia (Tier 1) to fill the gap.

### LOCAL-32 gains carried forward
- Structural-heading noun vocabulary (EN+FR, word-level, `_is_structural_heading`)
- Expanded `_WIKI_SECTION_HEADING_PATTERNS` regex (EN+FR generalisation)
- Rules 9 + 10 in `classify_corpus_entry` (structural heading + nav label)
- Visitor-info validity gate (`_is_valid_visitor_info`)
- English rendering of Matisse visitor info (month translations, ordinals, connectors)

---

## Acceptance Evidence

### Asian Arts Museum (MUST NOT REGRESS)
```
Stops: 8/8  ✓
  1. L'Armure d'Andô Naoyuki
  2. Statue de Bouddha
  3. La danse cosmique de Ganesh
  4. Kannon, le bodhisattva de la compassion
  5. Ulysses Grant au Japon
  6. Robe de prêtre taoïste
  7. Kannon à mille bras
  8. Masque du vieillard kojô
Museum Information: Closed on Tuesday. Free admission  ✓
```

### Matisse Museum
```
Stops: 8/8  ✓
  1. Nu bleu IV
  2. Nymphe dans la forêt
  3. Tempête à Nice
  4. Pierre Matisse, un marchand d'art à New York
  5. Odalisque au coffret rouge
  6. Lectrice à la table jaune
  7. Nature morte aux grenades
  8. Papeete-Tahiti
Museum Information: Open every day except Tuesday: from 10:00 to 17:00 from 1st November to 31 March from 10:00 to 18:00. Free  ✓
```

### Palais Lascaris
```
Stops: 6/8  ✓ (was 1 — substantial improvement)
  1. Raquel
  2. Basse de violon
  3. Harpe
  4. Most famous guitars
  5. Sacqueboute ténor
  6. Violes d'amour
Museum Information: (omitted — no valid info found at venue section)  ✓
Section headings as stops: 0  ✓
Municipal admin text: none  ✓
```

### URLs crawled for Palais Lascaris (scoping evidence)
```
[LOCAL-33] Deep-path URL detected — crawl scoped to: /fr/culture/musees-et-galeries/palais-lascaris-le-palais*
[story_miner] Site crawl: 1 pages fetched (budget: 15)

Source URLs:
  https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais
  https://en.wikipedia.org/wiki/Palais_Lascaris
  https://fr.wikipedia.org/wiki/Palais_Lascaris

NOT crawled (scoped out):
  /type-lieu/salles-de-sport/
  /sport/parcours/
  /contact/
  /agenda/
  /administration/tarifs-des-services-municipaux/
  /administration/publications-obligatoires/
```

### Visitor info for all three venues
- Asian Arts: `Closed on Tuesday. Free admission` — correct, English ✓
- Matisse: `Open every day except Tuesday: from 10:00 to 17:00 [...]. Free` — correct, English ✓
- Palais Lascaris: omitted (no valid info at scoped venue section) ✓

### Full regression
```
test_palais_fix_lead_fixture.py:  23/23 PASS
test_b6_generation_wiring.py:     14/14 PASS
test_f4_cache_roundtrip.py:       ALL PASS
test_g4_false_positives.py:       ALL PASS
test_sq2_fixtures.py:             ALL PASS
test_sq3_fixtures.py:             ALL PASS
test_sq4_merge.py:                ALL PASS
test_w4_matcher.py:               ALL PASS
test_w7_wiring.py:                ALL PASS
test_w9_collection_anchor.py:     ALL PASS
test_tier_computation.py:         ALL PASS
test_venue_identity.py:           11/11 PASS
test_spine_generator.py:          18/18 PASS
```

`test_attestation_log_only.py` and `test_contained_regression.py` fail on clean
`storied` — pre-existing (require running Docker services).
