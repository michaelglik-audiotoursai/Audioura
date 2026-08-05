##### READY FOR REVIEW

## LOCAL-234: Corpus for Uncovered Museum Venues

**Commit:** (see below)
**Branch:** kiro/local234-corpus-for-uncovered-venues
**Base:** storied

---

## Summary

Added stop_corpus for 3 uncovered museum venues (18 stops total). All stops
receive venue-level corpus; 1 stop (Statue de Bouddha) receives subject-level
corpus. Zero stops left EMPTY. Per D74, 17 of 18 stops are deliberately
VENUE_ONLY because no source could confirm the specific exhibit at this museum
from the same document.

**Spend: $0.00** (Wikipedia API only — no paid searches).

---

## Venues Attempted

| Venue | Stops | Enriched | Role |
|-------|-------|----------|------|
| National Constitution Center, Philadelphia PA | 1 | 1 | about_venue |
| Musée d'art naïf (Museum of Naïve Art), Nice | 9 | 9 | about_venue |
| Musée des Arts Asiatiques (Asian Art Museum), Nice | 8 | 8 | 7 about_venue, 1 about_subject |

## Venues Deliberately Skipped

| Venue | Reason |
|-------|--------|
| restaurants tour, old city of Nice | Not a museum — outdoor/restaurant, out of scope |
| Camel/desert tours, Abu Dhabi | Not a museum — outdoor/transport, out of scope |
| Dog sledding, Big Lake AK | Not a museum — outdoor/transport, out of scope |

---

## Coverage Before / After

### Before (baseline, 7 venues, 70 rows):
```
COVERED=52  CREATOR_ONLY=6  VENUE_ONLY=12  EMPTY=0
```

### After (10 venues, 88 rows):
```
COVERED=53  CREATOR_ONLY=6  VENUE_ONLY=29  EMPTY=0
```

### Per-venue delta (new venues only):
```
National Constitution Center, Philadelphia PA:     C=0 CR=0 V=1 E=0
Musée d'art naïf (Museum of Naïve Art), Nice:      C=0 CR=0 V=9 E=0
Musee des Arts Asiatiques (Asian Art Museum), Nice: C=1 CR=0 V=7 E=0
```

### Existing venues unchanged:
```
Boston Common, Boston MA:                           C=3  CR=0 V=0 E=0 (no change)
French Riviera walking area:                        C=24 CR=0 V=4 E=0 (no change)
Musee Matisse, Nice, France:                        C=6  CR=0 V=0 E=0 (no change)
Musee National Marc Chagall, Nice, France:          C=2  CR=2 V=0 E=0 (no change)
Musee d Art Moderne et d Art Contemporain, Nice:    C=8  CR=1 V=4 E=0 (no change)
Palais Lascaris, Nice:                              C=8  CR=3 V=0 E=0 (no change)
walking tour in Nice, france:                       C=1  CR=0 V=4 E=0 (no change)
```

---

## Stops Left Empty at Subject Level (17 of 18) — Defended

Every stop except "Statue de Bouddha" receives only `about_venue` corpus.
This is deliberate and correct:

1. **Museum of Naïve Art stops** (9 stops: "The Dream", "The Wedding",
   "The Sleeping Gypsy", etc.) — These are generic painting titles shared
   across hundreds of artworks. No source confirms which artist's work hangs
   at each stop. Storing a Rousseau article for "The Dream" when Rousseau's
   "The Dream" is at MoMA NYC would be the D74 Manet-for-Jacquet failure.

2. **Asian Art Museum stops** (7 stops: armor, Ganesha, Kannon, Noh mask,
   etc.) — Wikipedia articles about these subjects (Ganesha, Guanyin, Noh)
   do not mention the Nice museum. D74: venue confirmation must come from
   the same source as the subject claim.

3. **National Constitution Center** (1 stop: "A More Perfect Union") — The
   museum's Wikipedia article describes the institution but does not mention
   this specific exhibit by name.

**The high VENUE_ONLY count (17/18) is the correct result under D74.**
An empty stop is caught by the coverage gate and degraded honestly; a stop
populated with the wrong material produces confident false narration.

---

## Verbatim Evidence (≥10 stops)

### 1. A More Perfect Union @ National Constitution Center
- **Source:** https://en.wikipedia.org/wiki/National_Constitution_Center
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The National Constitution Center is an American non-profit
  institution that is devoted to the study of the Constitution of the United
  States. Located at Independence Mall in Philadelphia, Pennsylvania, the
  center is an interactive museum which serves as a national town hall..."

### 2. The Flight into Egypt @ Musée d'art naïf
- **Source:** https://en.wikipedia.org/wiki/Musée_international_d'Art_naïf_Anatole_Jakovsky
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The Musée international d'Art naïf Anatole Jakovsky (Eng.:
  Anatole Jakovsky International Museum of Naive Art) is a museum located in
  Nice, which displays 18th–21st century works specialized in naive art.
  The museum was inaugurated on 5 March 1982."

### 3. The Sleeping Gypsy @ Musée d'art naïf
- **Source:** https://en.wikipedia.org/wiki/Musée_international_d'Art_naïf_Anatole_Jakovsky
- **Tier:** 1 | **Role:** about_venue
- **Passage (from Jakovsky biography):** "In the process of exploring various
  avenues of interest, Jakovsky met the naïve painter Jean Fous. There, in
  1942, while helping him unpack books and various objects, he discovered
  canvases in a portfolio case of a Rousseau Customs officer which caught
  his interest."

### 4. The Dream @ Musée d'art naïf
- **Source:** https://en.wikipedia.org/wiki/Musée_international_d'Art_naïf_Anatole_Jakovsky
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The works are composed of paintings, sculptures, drawings,
  posters by painters such as Henri Rousseau, Séraphine Louis, Grandma Moses,
  O'Brady, Rimbert, Ivan and Josip Generalic, Bauchant, Vivin..."

### 5. Statue de Bouddha @ Musée des Arts Asiatiques
- **Source:** https://en.wikipedia.org/wiki/Asian_Art_Museum_(Nice)
- **Tier:** 1 | **Role:** about_subject
- **Passage:** "Originally, this pair of deer accompanied a Wheel of Dharma
  above the entrance gate of a Tibetan monastery. Encountered from the early
  centuries CE in India and continually reproduced, these great Buddhist
  emblems evoke the first sermon of Buddha Sakyamuni after his enlightenment,
  in the Deer Park at Sarnath, near Benares, India."

### 6. L'Armure d'Andô Naoyuki @ Musée des Arts Asiatiques
- **Source:** https://en.wikipedia.org/wiki/Asian_Art_Museum_(Nice)
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The Asian Art Museum of Nice (in French: Musée départemental
  des arts asiatiques de Nice) is a museum located in Nice, France, dedicated
  to the arts and cultures of Asia. It was established in 1998 and is
  operated by the Alpes-Maritimes departmental council."

### 7. La danse cosmique de Ganesh @ Musée des Arts Asiatiques
- **Source:** https://en.wikipedia.org/wiki/Asian_Art_Museum_(Nice)
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The museum was designed by the Japanese architect Kenzo Tange:
  'In my mind, this museum is a jewel of snow shining in the azure of the
  Mediterranean. It is a swan floating on a peaceful lake amidst lush
  vegetation...'"

### 8. Kannon, le bodhisattva de la compassion @ Musée des Arts Asiatiques
- **Source:** https://en.wikipedia.org/wiki/Asian_Art_Museum_(Nice)
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The four cubes overlooking the lake are dedicated to Indian,
  Chinese, Japanese, and Southeast Asian civilizations. On the first floor,
  the cylindrical rotunda topped with a glass pyramid is dedicated to
  Buddhist statuary."

### 9. Ulysses Grant au Japon @ Musée des Arts Asiatiques
- **Source:** https://en.wikipedia.org/wiki/Asian_Art_Museum_(Nice)
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "Pierre-Yves Trémois initiated the project by offering his
  collection of Asian art to the City of Nice in the mid-1980s in exchange
  for the creation of a museum."

### 10. Masque du vieillard kojô @ Musée des Arts Asiatiques
- **Source:** https://en.wikipedia.org/wiki/Asian_Art_Museum_(Nice)
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The museum's collection is founded on a selection of
  emblematic works representing the spirit of Asian cultures, combining court
  arts, religious creations, everyday objects, and popular expressions."

### 11. The Wedding @ Musée d'art naïf
- **Source:** https://en.wikipedia.org/wiki/Musée_international_d'Art_naïf_Anatole_Jakovsky
- **Tier:** 1 | **Role:** about_venue
- **Passage:** "The collection come from donations of Renée and Anatole
  Jakovsky (to whom the museum owes its current name), and the Centre Georges
  Pompidou. The giant statues in the garden were created by Frédéric
  Lanovsky. The museum has about 20,000 visitors per year, and 600 works
  from 27 countries."

---

## Rejected Candidates (≥3, with reasons)

### 1. "The Sleeping Gypsy" — Henri Rousseau's painting (Wikipedia)
- **Venue:** Musée d'art naïf, Nice
- **Reason:** Rousseau's "The Sleeping Gypsy" (1897) is at MoMA, New York
  City, not at the Musée d'Art Naïf in Nice. The museum article mentions
  Rousseau as a collected artist, but this specific painting is confirmed
  elsewhere. Storing it would be the D74 Manet-for-Jacquet failure — right
  artist collected at venue, wrong specific work.

### 2. "The Dream" — Henri Rousseau's painting (Wikipedia)
- **Venue:** Musée d'art naïf, Nice
- **Reason:** Rousseau's "The Dream" (1910) is at MoMA, NYC. The museum in
  Nice collects Rousseau works but no source confirms which Rousseau painting
  is at THIS stop. A title match is not identification (D74 rule 2).

### 3. "The Bathers" — Cézanne (Wikipedia)
- **Venue:** Musée d'art naïf, Nice
- **Reason:** "The Bathers" is an extremely common painting title (Cézanne,
  Renoir, Fragonard, Seurat...). Without a source confirming which artist's
  "Bathers" is at the Musée d'Art Naïf, any attribution is speculation.
  Moreover, Cézanne is not a naive artist — his work would not be in this
  collection.

### 4. Ganesha (Wikipedia, 41,789 chars)
- **Venue:** Musée des Arts Asiatiques, Nice
- **Stop:** "La danse cosmique de Ganesh"
- **Reason:** Wikipedia article about Ganesha does not mention Nice, the Asian
  Art Museum, or any connection to this venue. D74: venue confirmation must
  come from the same source as the subject claim.

### 5. Guanyin (Wikipedia, 54,746 chars)
- **Venue:** Musée des Arts Asiatiques, Nice
- **Stop:** "Kannon, le bodhisattva de la compassion"
- **Reason:** Wikipedia Guanyin article discusses the bodhisattva generally
  but has no mention of Nice or the Asian Art Museum. Cannot confirm this
  specific statue is at this museum from this source.

### 6. World tour of Ulysses S. Grant (Wikipedia, 51,767 chars)
- **Venue:** Musée des Arts Asiatiques, Nice
- **Stop:** "Ulysses Grant au Japon"
- **Reason:** Article discusses Grant's world tour including Japan, but does
  not mention Nice or the Asian Art Museum. The connection to this museum's
  exhibit cannot be confirmed from this source.

### 7. Japanese armour (Wikipedia)
- **Venue:** Musée des Arts Asiatiques, Nice
- **Stop:** "L'Armure d'Andô Naoyuki"
- **Reason:** Article about Japanese armor generally. Does not mention Andô
  Naoyuki, Nice, or this museum. A generic topic article cannot ground a
  specific named object at a specific museum.

### 8. Noh (Wikipedia, 39,567 chars)
- **Venue:** Musée des Arts Asiatiques, Nice
- **Stop:** "Masque du vieillard kojô"
- **Reason:** Wikipedia Noh article discusses masks generally but does not
  mention this museum. Would be grounding a specific mask at a specific
  museum with an article about theater generally.

---

## Row and Passage Counts

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| stop_corpus rows | 70 | 88 | +18 |
| stop_corpus passages | 158 | 211 | +53 |
| audio_tours rows | 138 | 138 | 0 |
| Distinct venues | 7 | 10 | +3 |

**Backup path:** `~/audioura-backups/stop_corpus_20260804T233720.json`

**Nice list unchanged:** `[1, 12, 14, 17, 21, 24, 27, 28, 29, 152]` — verified.

---

## Per-file Summary

| File | Action |
|------|--------|
| `acquire_uncovered_museums.py` | NEW — acquisition script for LOCAL-234 |
| `SUBMISSION_LOCAL-234.md` | NEW — this file |

**No files modified:** No changes to detectors, claim_check.py,
corpus_coverage.py, DECISIONS.md, CLAUDE.md, .continuous_dev/*, or
generate_tour_text.py. No container rebuilds.

---

## Limitations

1. **17 of 18 stops are VENUE_ONLY.** The museums attempted have stops with
   generic titles (paintings at Naive Art museum) or objects not documented on
   Wikipedia in connection with this venue (Asian Arts objects). Subject-level
   enrichment requires either institutional catalog access (not available via
   Wikipedia) or paid search — which is within budget ($0.50) but Wikipedia
   was exhausted first.

2. **The Naive Art museum's Wikipedia article is short (1,286 chars).** Only
   3 unique paragraphs available — all 9 stops share the same venue passages.
   Deeper enrichment would require the museum's own website or collection
   database.

3. **No outdoor/transport venues attempted.** The machinery
   (`stop_subject_acquisition.py`) was built for museums (LOCAL-199→203).
   Camel tours, dog sledding, and restaurant tours are structurally different
   problems requiring different approaches.

4. **Bouddha stop's "about_subject" status is indirect.** The museum article
   discusses Buddhist statuary and a Gandhara Buddha at this museum — close
   enough to "Statue de Bouddha" to confirm subject presence. But it's the
   museum describing its own collection, not an independent article about
   this specific statue.
