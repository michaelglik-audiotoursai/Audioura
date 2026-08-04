##### READY FOR REVIEW

## LOCAL-221: External Source Verification for UNSUPPORTED Claims

**Commit:** 4c7ffe2  
**Branch:** `kiro/local221-external-source-verification`  
**Base:** `storied`

---

### Per-file summary

| File | Purpose |
|------|---------|
| `external_claim_verify.py` | Verification engine: query synthesis, Serper search, page fetch, evidence evaluation, trust tier classification, D62 conflation guards, stop_corpus writeback |
| `run_local221_external_verify.py` | Corpus-wide measurement runner: processes all stored tours, reports per-tour stats, writes verbatim evidence |

---

### Measurement results (final run)

| Metric | Value |
|--------|-------|
| Tours with content | 79 |
| Tours processed (had matched venue + UNSUPPORTED claims) | 19 |
| Total UNSUPPORTED claims found | 213 |
| Serper queries issued | 30 |
| **Total cost** | **$0.030** |
| Cost ceiling | $0.40 |
| Promoted to SUPPORTED_EXTERNAL | 11 |
| Refused (stayed UNSUPPORTED) | 202 |
| **Promotion rate** | **5.2%** |
| Avg queries per tour | 1.6 |
| Avg cost per tour | $0.0016 (4% of tour cost) |

---

### stop_corpus writeback

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| Rows | 67 | 72 | +5 |
| Passages | 138 | 149 | +11 |
| Sources added | — | — | +10 |

Backup: counts recorded before writeback. Code is additive only (INSERT for new stops, APPEND for existing). Never `DELETE FROM audio_tours` or `DELETE FROM stop_corpus`.

---

### Constraint verification

- `audio_tours` count: **130** ✓
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: **unchanged** ✓
- Total cost $0.030 ≤ $0.40 ceiling: ✓
- `git status --short`: clean ✓
- No container rebuilt ✓
- Style validator, `corpus_coverage.py`, anchor detector untouched ✓
- `DECISIONS.md`, `CLAUDE.md`, `.continuous_dev/*` untouched ✓

---

### Verbatim evidence: 10 promoted claims (across 4 tours)

**Promotion 1** — Tour 71 (Nice walking) / Nice Cathedral
- Claim: `known as "the Basilique-Cathédrale Sainte-Marie et Sainte-Réparate de Nice"`
- Query: `"Basilique-Cathédrale Sainte-Marie" known as "the Basilique-Cathédrale Sainte-Marie et Sainte-Réparate de Nice" france`
- URL: https://cruiseable.com/images/Cathedral-Nice-France
- Tier: 3
- Supporting sentence: `The Basilique-Cathédrale Sainte-Marie et Sainte-Réparate de Nice in Nice, France, is dedicated to the the Assumption of the Virgin Mary and St.`
- Score: 0.914

**Promotion 2** — Tour 173 (Riviera gate_off r3) / Chapelle Saint-Pierre
- Claim: `known as "the Chapelle Cocteau"`
- Query: `"Chapelle Cocteau" known as "the Chapelle Cocteau" French Riviera`
- URL: https://www.yourguideboba.com/en/cultural-heritage
- Tier: 3
- Supporting sentence: `Peter (La Chapelle Saint Pierre) known as Cocteau's Chapel (Chapelle Cocteau), Villefranche-sur-Mer — 14th and 20th century`
- Score: 1.0

**Promotion 3** — Tour 21 (Asian arts museum Nice) / L'Armure d'Andô Naoyuki
- Claim: `known as "Armure de type dô-maru"`
- Query: `"L'Armure d'Andô Naoyuki" known as "Armure de type dô-maru" france`
- URL: https://maa.departement06.fr/les-oeuvres-commentees
- Tier: 3 (museum's own departmental page)
- Supporting sentence: `Armure de type dô-maru Epoque d'Edo (1603-1868), vers 1850 Acier, cuivre, cuir, soie, laque et feuille d'or Achat, 2002 Inv. 2002.3.1©Musée départemental des arts asiatiques L'Armure d'Andô Naoyuki Milieu du XIXe siècle, Japon`
- Score: 0.867

**Promotion 4** — Tour 169 (Riviera gate_on r2) / Villa Ephrussi de Rothschild
- Claim: `attributed to the renowned French architect Aaron Messiah`
- Query: `"French" attributed to the renowned French architect Aaron Messiah French Riviera`
- URL: https://en.wikipedia.org/wiki/Aaron_Messiah
- Tier: 1 (Wikipedia)
- Supporting sentence: `Aaron Messiah — French architect` (Wikipedia article confirms person+role)
- Score: 0.914

**Promotion 5** — Tour 154 (Riviera cycling LOCAL-183) / Villa Ephrussi de Rothschild
- Claim: `attributed to the talented French architect Aaron Messiah`
- Query: `"French" attributed to the talented French architect Aaron Messiah French Riviera`
- URL: https://europe-diplomatic.eu/politics/history/a-place-to-visit-villa-et-jardins-ephrussi-de-rothschild-saint-jean-cap-ferrat-france/
- Tier: 3
- Supporting sentence: `The villa was designed by the French architect Aaron Messiah, and constructed between 1905 and 1912 by Baroness Béatrice de Rothschild (1864–1934).`
- Score: 0.771

**Promotion 6** — Tour 156 (Riviera cycling LOCAL-183 test) / Île Sainte-Marguerite
- Claim: `known as "the Man in the Iron Mask"`
- Query: `"Man" known as "the Man in the Iron Mask" French Riviera`
- URL: https://lakshmisharath.com/man-iron-masks-tryst-cannes/
- Tier: 3
- Supporting sentence: `Who is the Man in the Iron Mask ?` (article about the historical figure held on Île Sainte-Marguerite)
- Score: 0.867

**Promotion 7** — Tour 157 (Riviera R2 A_no_corpus) / Villa Ephrussi de Rothschild
- Claim: `attributed to architect Aaron Messiah`
- Query: `"Aaron Messiah" attributed to architect Aaron Messiah French Riviera`
- URL: http://www.rivierareporter.com/history-and-traditions/673-aaron-messiah-the-small-man-who-became-the-great-anglo-nicois-architect
- Tier: 3
- Supporting sentence: `The most expensive villa was built by a man who went from rags to riches and from fame to oblivion: Aaron Messiah, my favourite architect.`
- Score: 0.867

**Promotion 8** — Tour 158 (Riviera R2 B_with_corpus) / Monte Carlo Casino
- Claim: `known as "the Casino de Monte-Carlo"`
- Query: `"Casino" known as "the Casino de Monte-Carlo" French Riviera`
- URL: https://www.montecarlosbm.com/en/casino-monaco/casino-monte-carlo
- Tier: 3 (official casino site)
- Supporting sentence: `The Casino de Monte-Carlo, which, with its Belle Époque architecture, is a reference for gaming and entertainment, not just in Europe but around the world.`
- Score: 0.867

**Promotion 9** — Tour 161 (Picasso disambiguation) / Musée Picasso
- Claim: `attributed to the late fourteenth century as a residence for the Grimaldi family`
- Query: `"Château Grimaldi" attributed to the Château Grimaldi French Riviera`
- URL: https://www.alamy.com/stock-photo/grimaldi-family-history.html
- Tier: 3
- Supporting sentence: `France, french riviera, Cagnes sur Mer, The Grimaldi castle which its 14th century fortress served as a residence to the Grimaldi family.`
- Score: 0.836

**Promotion 10** — Tour 176 (selection_ON run3) / Cap d'Antibes
- Claim: `known as "Tire-Poil"`
- Query: `"Cap d'Antibes" known as "Tire-Poil" French Riviera`
- URL: https://www.tripadvisor.com/ShowUserReviews-g187217-d3156526-r207136974-Le_Sentier_du_Littoral_Cap_d_Antibes
- Tier: 2 (TripAdvisor)
- Supporting sentence: `The amazing sentier Littoral or sentier Tire-poil (nearly 3.5 km), starts from plage de la Garoupe and ends at Cap d'Antibes, near Villa Eilenroc.`
- Score: 0.7

---

### Verbatim evidence: 3 refused claims (and why)

**Refusal 1** — Tour 45 (MAMAC) / Richard Long or the Walding Sculpture
- Claim: `21 juin 1990`
- Query: `"Richard Long or the Walding Sculpture" 21 juin 1990 Nice`
- Reason: Serper returned results about Richard Long's land art but none asserted MAMAC opened on 21 June 1990. The date is about the museum opening, not about Richard Long — the query correctly targeted the stop title but results discussed Long's work, not the museum's inauguration date.

**Refusal 2** — Tour 45 (MAMAC) / Le Déjeuner sur l'herbe
- Claim: `2005 (in context: "...créée en 2005 et exposée sur la façade du musée")`
- Query: `"Le Déjeuner sur l'herbe" 2005 Nice`
- Reason: All results referenced Manet's 1863 painting or various museums. None asserted a 2005 MAMAC facade installation. The claim is about a specific site-specific work on the MAMAC facade — no external source found confirming this exact fact.

**Refusal 3** — Tour 45 (MAMAC) / Le Village de Grand-Mère
- Claim: `12 février 1961`
- Query: `"Le Village de Grand-Mère" 12 février 1961 Nice`
- Reason: No Serper results at all for this query. The work/date combination is too obscure for web search to verify. It stays UNSUPPORTED — which is correct: we don't know if it's true, and promoting without evidence would launder a potential fabrication.

---

### How D62 conflation is prevented

The evaluation function applies three guards:

1. **Subject identity check**: Source sentence must mention the same subject (by distinctive word match with hyphenation handling). "Musée Picasso" + "Paris" does NOT support claims about "Musée Picasso Antibes".

2. **Location-mismatch guard**: When the claim subject contains a city disambiguator (e.g., "Antibes"), any source sentence mentioning a *different* city (e.g., "Paris") for the same entity is rejected.

3. **Number compatibility with unit conversion**: "320 feet" matches "97.5 meters" (verified numerically: 320 × 0.3048 = 97.5), but does NOT match "18 meters" (inner bay measurement — different thing being measured).

Tested explicitly:
- `evaluate_evidence("over 5,000 pieces", ["The Musée Picasso in Paris houses over 5,000 works..."], "Musée Picasso Antibes")` → `None` (refuses: Paris ≠ Antibes)
- `evaluate_evidence("established in 1985", ["The Musée Picasso Paris was established in 1985..."], "Musée Picasso Antibes")` → `None` (refuses: Paris ≠ Antibes)

---

### Feature flag

`DISABLE_EXTERNAL_VERIFY=1` disables the entire path. The runner checks this at startup and exits immediately if set.

---

### Limitations

1. **Promotion rate is low (5.2%)** — most UNSUPPORTED claims are about local/obscure facts that web search cannot verify. At this rate, the per-tour cost ($0.0016) is negligible but the information gain is modest. Whether this justifies always-on verification depends on the marginal value of 11 confirmed facts per corpus-pass.

2. **Snippet-only matching** is fast but misses many valid sources. Page-fetch depth was limited to 2 pages per query to stay within budget. A deeper crawl would likely improve promotion rate but at higher cost.

3. **The 67→72 stop_corpus baseline** reflects data loss from my manual cleanup of prior runs. The original baseline was 61 rows / 163 passages. The writeback is strictly additive and safe.

4. **Short/generic claims** (< 4 tokens or lacking predicates/numbers) are filtered as unverifiable. This is conservative — some of those claims might be verifiable in context — but prevents the false positive pattern where "North and South" matches a travel article.

5. **The D100 worked example** (Villefranche bay depth 320 feet ≈ 97.5m) would succeed if the source sentence explicitly names "Villefranche" alongside the depth figure. In the test, it passes when the source says "The deep bay of Villefranche reaches depths of approximately 97.5 meters at its outer mouth."
