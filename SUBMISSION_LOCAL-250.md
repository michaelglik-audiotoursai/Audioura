##### READY FOR REVIEW

## LOCAL-250: Expand before delete — the missing half of Michael's routine (v2)

**Branch:** `kiro/local250-expand-before-delete`
**Base:** `storied`

### What was built

Between R10 detection and deletion, the script now queries the corpus for a fact
that would substantiate the flagged promise-sentence. If found, an LLM rewrites
the sentence around that fact (the LLM may only phrase, never supply). If not
found, deletion fires as before.

**v2 fixes (LEAD bounce 2026-08-05):**
1. **Dedup rule:** One corpus passage may substantiate ONE sentence per tour. If a
   second flagged sentence matches only a spent passage, it is deleted.
2. **Stop count validation:** Generation retries up to 3 times if stop count < requested.
3. **Label stripping:** "Description:" field labels stripped from narration post-generation.

### Commit

```
ae7cf55 LOCAL-250 v2: dedup, stop-count retry, label stripping (LEAD bounce fixes)
d36cd22 LOCAL-250: expand before delete — corpus lookup between R10 detection and deletion
```

### Per-file summary

| File | Change |
|------|--------|
| `run_local250_expand_before_delete.py` | Rewritten: dedup (spent_passages set), stop-count retry loop, Description: stripping, expanded investigations (bounce items 4 & 5) |
| `RIVIERA_2STOP_ROUND7.md` | Regenerated: 2 stops, 658 words, dedup evidence, bounce fix report |
| `tours/LOCAL250_riviera_2stop_round7.txt` | Regenerated tour text: 2 stops, no Description: leak, Fitzgerald appears once |
| `tours/LOCAL250_riviera_2stop_round7_evidence.json` | Expansion log with dedup metadata |

### Verbatim evidence

#### Boundary rows (9/9 pass)
```
  --- MUST FIRE (promise, unsubstantiated) ---
    ✓ FIRES subjects=['secrets']: "As you cycle along the coastal path..."
    ✓ FIRES subjects=['grandeur', 'introspection', 'stories']: "The Villa Ephrussi..."
    ✓ FIRES subjects=['elegance', 'facets', 'opulence']: "These stops reveal..."
    ✓ FIRES subjects=['allure', 'stories']: "The coastline holds stories..."

  --- MUST STAY SILENT ---
    ✓ SILENT: "In January 1888, Claude Monet painted the same shoreline..."
    ✓ SILENT: "The Hôtel du Cap-Eden-Roc was built in 1870..."
    ✓ SILENT: "Start cycling south on the main road..."
    ✓ SILENT: "The Rue Obscure is a 130-metre fortified street..."
    ✓ SILENT: "Èze was first settled near Mount Bastide around 200 BC."

  ALL 9 BOUNDARY ROWS PASS ✓
```

#### Expand/delete log
```
Stop 1: Cap d'Antibes (7 corpus passages available)
  R10 FIRES: "You are about to embark on a journey..." subjects=['secrets','tapestry']
    → DELETED_NO_CORPUS (no passage matches)
  R10 FIRES: "Feel the Mediterranean breeze at the spot where Picasso..." subjects=['allure','story']
    → EXPANDED using: "For France lovers, Fitzgerald's Tender is the Night (1934)..."
    → "Discover the charm of Cap d'Antibes, a place that inspired Fitzgerald's portrayal of the Roaring Twenties in his novel Tender is the Night, published in 1934."
  R10 FIRES: "Cap d'Antibes embodies the essence..." subjects=['essence','tapestry']
    → DELETED_NO_CORPUS (all matching passages spent)
  R10 FIRES: "Cycling along the coastal road offers glimpses of the allure..." subjects=['allure']
    → DELETED_NO_CORPUS (all matching passages spent)

Stop 2: Saint-Paul-de-Vence (1 corpus passage available)
  R10 FIRES: "Descending the winding paths..." subjects=['secrets','stories']
    → DELETED_NO_CORPUS (passage does not match subject)
```

#### Dedup verification
```
Passages spent: 1 (Fitzgerald's Tender is the Night)
Fitzgerald appears in final output: 1 time (confirmed via grep)
Round 7 v1 had: 3 times (same passage used 3x — the bug)
```

#### Residuals
```
  R1: 1/4 paragraphs
  R7: 0
  R8: 0
  R9: 0
  R10: 0
```

#### DB safety
```
  audio_tours before: 142
  audio_tours after:  142
  Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
  No rows created — nothing to clean (D141)
```

#### Stop count and word count
```
  Stops: 2 (Cap d'Antibes, Saint-Paul-de-Vence)
  Words: 658 (R5: 680, R6: 298)
  Generation attempts: 3/3 (stops validated per attempt)
```

#### Cost
```
  Generation: $0.0097
  Expansion:  $0.0001
  Total:      $0.0098 (ceiling: $0.60)
```

### Bounce fixes verification

| Bounce item | Status | Detail |
|-------------|--------|--------|
| 1. Only 1 stop | FIXED | Retry loop validates stop count; 3 attempts needed this run. 2 stops in output. |
| 2. Duplicate Fitzgerald | FIXED | Dedup: spent_passages set prevents reuse. Fitzgerald appears 1x in final output. |
| 3. Description: leaked | FIXED | Post-processing strips leaked field labels. grep confirms 0 occurrences. |
| 4. Tour-Category: walking | INVESTIGATED | Same in round 6 (storied base). By design: internal template classifier. Not a regression. |
| 5. R7 on orientation | INVESTIGATED | Orientation IS in residual scope. R7 does NOT fire on this sentence (pattern incomplete). Phase 5.95 does not gate R7. |

### Defect investigations (from original task)

**Defect 1 (R7 "waves lapping"):** R7 fires, R10 does not. R10 is the deletion
gate; R7 has no deletion path. Orthogonal rules: R7 detects invented sensory;
R10 detects unfulfilled promise. Fix needed: R7 deletion path (separate task).

**Defect 2 (smuggler's tunnels dual path):** Prolog version uses "whispers...secrets"
→ R10 fires. Stop version uses bare assertion → R10 silent. Same claim, two syntactic
shapes. A truth gate for assertions is a separate task.

### Limitations

- **Expansion yield is low** (1/5 flagged sentences expanded). The corpus for this
  tour has only 7 unique passages for Cap d'Antibes and 1 for Saint-Paul-de-Vence,
  with heavy duplication (Monet appears twice, Tire-Poil appears twice). With dedup,
  only one passage from each cluster is usable. Richer corpora will yield more.
- **Stop selection is non-deterministic.** Round 6 had Saint-Jean-Cap-Ferrat as stop 2;
  round 7 has Saint-Paul-de-Vence. The generator's POI selection depends on LLM outputs
  and the existence gate (Promenade des Anglais is repeatedly rejected by LOCAL-22).
- **R7 pattern set is incomplete** — invented sensory like "salty tang of the Mediterranean"
  passes because R7's patterns target specific phrases, not general sensory invention.
