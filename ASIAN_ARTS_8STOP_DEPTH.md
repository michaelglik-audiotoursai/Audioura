# Asian Arts Museum — 8-Stop Corpus Depth Measurement (LOCAL-254)

## Generation outcome

Tour generation was attempted with all gates ON (STORIED_MODE=true, no
overrides). **Generation returned None** — the D1v2 pipeline classified the
venue as `unresolvable`.

## Why generation is blocked (two independent causes)

### Cause 1: D1v2 venue resolution fails on the parenthetical name

The `venue_resolver.resolve_venue()` function CAN resolve this museum:
```
resolve_venue("Musee des Arts Asiatiques", "Nice")
→ Q3330160 (Asian Arts Museum), URL: https://maa.departement06.fr/
```

But the generation pipeline passes the **full stored name** including the
English parenthetical:
```
"Musee des Arts Asiatiques (Asian Art Museum)"
```

The Wikidata search API returns zero candidates for that string. The resolver
logs `No Wikidata candidates for 'Musee des Arts Asiatiques (Asian Art Museum)'`
three times (strict, relaxed, single-word attempts), and returns `None`. The
pipeline then finds 0 canonical titles and sets tier to `unresolvable`.

**Fix (out of scope):** Strip parenthetical suffixes before passing to the
resolver, or add a name-normalization step.

### Cause 2: Stop-existence gate verifies 0 of 8 stops

Even if venue resolution were fixed, the existence gate would verify no stops.
The gate has two paths:

**Path 1 (venue_corpus canonical titles):** No `venue_corpus` row exists for
Q3330160. This path cannot fire at all.

**Path 2 (stop_corpus D74 same-source rule):** A passage must mention BOTH the
stop subject AND the venue in the same text. For `L'Armure d'Ando Naoyuki`:

- Passage [0] mentions the museum ("Asian Art Museum of Nice") → has_venue=True
- But no passage contains "armure", "ando", or "naoyuki" → has_stop=False
- D74 requires BOTH → verdict: unverified

The same pattern holds for all 4 verified stops. Their passages describe the
museum building and collection history but never name the specific objects.

**Fix (out of scope):** Create a `venue_corpus` row for Q3330160 with
`canonical_titles_json` listing the verified stop titles. This lets path 1
verify them instantly without needing object-specific prose in every passage.

### This is not a regression

The gate was 0/8 before LOCAL-254 started and is 0/8 after. The corpus
enrichment is stored and ready; the blockers are (1) name parsing and (2)
missing `venue_corpus` registration — both separate from corpus depth.

## Corpus state (after bounce fix)

| Stop | Passages | URLs | Verified by gate |
|------|----------|------|-----------------|
| L'Armure d'Ando Naoyuki | 5 | all | No |
| Statue de Bouddha | 6 | all | No |
| La danse cosmique de Ganesh | 5 | all | No |
| Robe de pretre taoiste | 5 | all | No |
| **Ulysses Grant au Japon** | **0** | — | No (D127 fabrication) |
| **Kannon, le bodhisattva de la compassion** | **0** | — | No (D127 fabrication) |
| **Kannon a mille bras** | **0** | — | No (D127 fabrication) |
| **Masque du vieillard kojo** | **0** | — | No (D127 fabrication) |

**Verified passages available: 21** (across 4 legitimate stops, mean 5.25)
**Fabrication stops: 4** (all at 0 passages, listed as unverifiable)
**Stops the gate would admit: 0 of 8** (neither pre- nor post-LOCAL-254)

## Hand-counted fact tallies

No tour text was generated (blocked at venue resolution). Per-stop fact tallies
cannot be measured until the two blockers above are resolved.

## What the before/after comparison IS

| | before | after |
|---|---|---|
| passages available across 8 stops | 33 (incl. 12 URL-less on fabrications) | 21 (clean) |
| passages on verified stops only | 21 | 21 (unchanged) |
| passages on fabrication stops | 12 (URL-less, generic) | 0 (removed) |
| stops rejected by existence gate | 8 of 8 | 8 of 8 (not a regression) |
| sentences carrying a fact | — (blocked) | — (blocked) |

## Unverifiable stops (task requirement: listed explicitly)

These stop names cannot be verified against any public source as objects held by
the Musée des Arts Asiatiques de Nice:

1. **Ulysses Grant au Japon** — D127: the Chikanobu triptych depicting Grant's
   reception exists but is held by the MFA Boston and the Met, not Nice.
2. **Kannon, le bodhisattva de la compassion** — No museum catalogue, Wikipedia,
   or Joconde record ties a Kannon bodhisattva to this museum.
3. **Kannon a mille bras** — Same: no public source confirms a thousand-armed
   Kannon at this specific museum.
4. **Masque du vieillard kojo** — No public source confirms a Noh kojo mask at
   this museum. The passages it had carried no URLs and described unrelated
   objects (a Toraja sarcophagus, a Cambodian deity statue).

These stops retain 0 passages. The existence gate correctly rejects them.
A passage that made any of these look sourced would launder a fabrication.
