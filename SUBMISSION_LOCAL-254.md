##### READY FOR REVIEW

## LOCAL-254: Corpus Depth for Nice Museums

**Branch:** kiro/local254-corpus-depth-museums  
**Base:** storied  
**Commit:** b4d6539 LOCAL-254: corpus depth for Palais Lascaris, Asian Arts, Matisse

---

## Per-file summary

| File | Purpose |
|------|---------|
| `run_local254_palais_lascaris.py` | Enriches 11 stops from Wikipedia + heritage portal + museum site |
| `run_local254_asian_arts.py` | Enriches 4 verifiable stops; marks 4 as fabrication (D127) |
| `run_local254_matisse.py` | Enriches 6 stops from Wikipedia |
| `run_local254_generate_asian_arts.py` | Generation attempt (all gates ON); documents D1v2 failure |
| `ASIAN_ARTS_8STOP_DEPTH.md` | Measurement doc for Asian Arts generation attempt |
| `SUBMISSION_LOCAL-254.md` | This document |

---

## BEFORE / AFTER corpus counts

| Venue | stops | before (passages) | after (passages) | mean before | mean after |
|-------|-------|-------------------|-----------------|-------------|------------|
| Palais Lascaris | 11 | 11 | 63 | 1.0 | 5.7 |
| Asian Arts Museum | 8 | 23 | 33 | 2.9 | 4.1 |
| Matisse Museum | 6 | 6 | 42 | 1.0 | 7.0 |
| **Total across 3 venues** | **25** | **40** | **138** | **1.6** | **5.5** |

Full stop_corpus: 88 rows, 338 total passages.

---

## Verbatim evidence (representative passages with sources)

### Palais Lascaris

**Wikipedia passage:**
> "Built in the first half of the seventeenth century and altered in the eighteenth century, the palace was owned by the Vintimille-Lascaris family until 1802. In 1942, it was bought by the city of Nice..."

Source: https://en.wikipedia.org/wiki/Palais_Lascaris

**Heritage portal passage:**
> "une sacqueboute tenor d'Anton Schnitzer (1581), la plus ancienne conservee au monde en l'etat d'origine."

Source: https://portail-savoirs.departement06.fr/annuaire-general/la-collection-dinstruments-de-musique-du-palais-lascaris

**Museum official site passage:**
> "Le Palais Lascaris presente les plafonds peints et les decors d'apparat du XVIIe et XVIIIe siecle. Le salon noble du premier etage presente des peintures murales attribuees a Giovanni Battista Carlone."

Source: https://www.nice.fr/lieux/palais-lascaris/

### Asian Arts Museum

**Wikipedia passage:**
> "The museum was designed by the Japanese architect Kenzo Tange (1913-2005) and inaugurated on October 16, 1998. Adjacent to a floral park, the building sits above an artificial lake and gives the illusion of floating on the water."

Source: https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29

**Wikipedia passage (collection method):**
> "The museum's design is based on two fundamental geometric shapes of Japanese tradition: the square, symbolizing earth, and the circle, symbolizing the sky. The four cubes overlooking the lake are dedicated to Indian, Chinese, Japanese, and Southeast Asian civilizations."

Source: https://en.wikipedia.org/wiki/Asian_Art_Museum_%28Nice%29

### Matisse Museum

**Wikipedia passage (museum):**
> "The Musée Matisse is located at 164 Avenue des Arènes de Cimiez in Nice, France. It opened in 1963 in the Villa des Arènes, a seventeenth-century building constructed between 1670 and 1685."

Source: https://en.wikipedia.org/wiki/Mus%C3%A9e_Matisse_(Nice)

**Wikipedia passage (artist biography):**
> "'Odalisque au coffret rouge' (Odalisque with Red Box) belongs to Matisse's series of odalisque paintings created during the 1920s in Nice. These works were inspired by his travels to Morocco in 1912-1913."

Source: https://en.wikipedia.org/wiki/Henri_Matisse

---

## Suspected fabrication stops (Asian Arts, D127)

These stop names were present in the existing corpus but could not be verified against any public source as objects in this specific museum:

- Ulysses Grant au Japon
- Kannon, le bodhisattva de la compassion
- Kannon a mille bras
- Masque du vieillard kojo

These were deliberately NOT enriched. They retain their original 3 generic passages each.

---

## Limitations

1. **Asian Arts generation blocked by D1v2 gate.** The venue resolver cannot find "Musee des Arts Asiatiques (Asian Art Museum)" in Wikidata. The pipeline returns `unresolvable` tier and produces no tour text. The corpus enrichment is stored and ready but cannot be exercised until the venue resolver is extended.

2. **No hand-counted fact density for Asian Arts.** Because generation was blocked, there is no generated text to measure.

3. **Palais Lascaris and Matisse generation not attempted in this commit.** The corpus enrichment for these venues was verified in prior LOCAL-252 work showing corpus depth drives factual density (7/8 facts from 7-passage corpus vs 2/11 from thin corpus). The enrichment scripts are deterministic and idempotent.

4. **Ceiling: $0.60.** The single generation attempt cost ~$0.0006 (696 tokens for Phase 3A POI fetch). Well under ceiling.

---

## Data integrity statement

No model-written passages. All passages extracted verbatim from:
- Wikipedia (en.wikipedia.org) — Tier 1
- Heritage portal (portail-savoirs.departement06.fr) — Tier 2
- Museum official site (nice.fr) — Tier 1

audio_tours table: 142 rows before and after. No tours created or modified.
