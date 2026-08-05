# Asian Arts Museum — 8-Stop Corpus Depth Measurement

## Corpus enrichment result

| | before | after |
|---|---|---|
| passages available across the 8 stops | 23 | 33 |
| stops rejected by the existence gate | — | venue unresolvable (D1v2 tier: unresolvable) |
| sentences carrying a fact, hand-counted, per stop | — | generation blocked — see below |
| words | — | generation blocked |

## Generation outcome

Tour generation was attempted with all gates ON (STORIED_MODE=true, no overrides disabled). The pipeline reached Phase 3A (candidate POI fetching) but the D1v2 existence gate classified the venue as **unresolvable** because:

1. No Wikidata candidates were found for "Musee des Arts Asiatiques (Asian Art Museum)"
2. No canonical titles could be discovered via SPARQL
3. The tier was set to `unresolvable`, triggering a clean fail

The generation returned `None` — no tour text was produced.

## Interpretation

The corpus depth enrichment succeeded (23 → 33 passages, mean 2.9 → 4.1 per stop). However, the D1v2 venue resolver cannot find this museum in Wikidata, so the generation pipeline rejects it before any stop selection occurs.

This means the existence gate is working correctly — it refuses to generate tours for venues it cannot verify. The fabricated stops ('Ulysses Grant au Japon', 'Kannon, le bodhisattva de la compassion', 'Kannon a mille bras', 'Masque du vieillard kojo') are moot since no tour is generated at all.

## What this tells us about corpus depth

The corpus enrichment is a necessary but not sufficient condition for tour generation:
- **Palais Lascaris**: venue IS resolvable (Wikipedia article exists, multiple sources) → generation possible
- **Matisse**: venue IS resolvable → generation possible
- **Asian Arts**: venue NOT resolvable by D1v2 → generation blocked at venue level, corpus enrichment still stored for future use

The 33 enriched passages remain in `stop_corpus` and will take effect if/when the venue resolver is extended to handle this museum.
