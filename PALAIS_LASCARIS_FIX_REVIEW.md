# Palais Lascaris Tour Generation Fix — LEAD Review Document

## Symptoms

**Reported by:** Michael (via Mobile Kiro)  
**Date:** 2026-07-14  
**Version:** v2.2.0+1 (storied branch, local Docker)

Two attempts to generate a museum tour for Palais Lascaris in Nice both failed:
1. `"Palais Lascaris, Nice, France"` → "no stops could be generated (all filtered or knowledge insufficient)"
2. `"Musee du Palais Lascaris, Nice, France"` → same error

The Palais Lascaris is a well-known 17th-century Baroque palace/museum in Nice's Old Town with baroque paintings, a musical instrument collection, and period furnishings. It's well-documented on the internet and in GPT's knowledge.

## Root Cause Analysis

### The failure chain (traced from Docker container logs):

1. **PHASE 3A** correctly identifies the venue via Wikidata (`Q34653010` → Musée du Palais Lascaris) and proposes 7 candidate artworks (The Annunciation, The Adoration of the Magi, The Holy Family, etc.)

2. **D1v2 verification** checks these candidates against Wikidata's artwork catalog for this museum. Wikidata only lists **1 work** for this museum (`"Raquel"`). Result: 6/7 candidates **DROPPED** with "no canonical title match". Tier = `thin`.

3. **R4 (bounded replenishment)** sees `tier=thin` → caps `total_stops = len(poi_list) = 1`. Does NOT attempt to replenish.

4. **BLOCKER1 (single-venue validation)** checks if stops look like other venues. With `poi_list` having only 1 item, the threshold `suspect_venues >= len(poi_list) // 2` = `0 >= 0` = **always true**, triggering rejection even with ZERO suspect venues.

5. **Result:** Pipeline returns `None` → service reports "no stops could be generated"

### Why this only affects museums with sparse Wikidata:

The D1v2 verification layer was designed to prevent GPT from hallucinating non-existent artworks. It works well for major museums (Centre Pompidou: 50+ works in Wikidata; MoMA: hundreds). But smaller/niche museums like Palais Lascaris have minimal Wikidata coverage (1 artwork listed) despite being real, well-documented venues with many exhibits.

The original design implicitly assumed "if Wikidata doesn't list a work, it doesn't exist in this museum" — which is false for smaller institutions.

## Fixes Applied

### Commit: `49c5a9a` — "Fix: thin-tier museums with sparse Wikidata no longer zero-stop-reject"

**Three changes in `generate_tour_text.py`:**

### Fix 1: Thin-tier degraded mode (D1v2 filtering)

When D1v2 returns `tier=thin` with < 3 verified works but GPT proposed ≥ 3 candidates:
- Restore the original GPT candidates alongside the verified ones
- Verified works go first, unverified follow (capped at +5)
- The venue IS Wikidata-resolved (it's a real museum), so GPT's knowledge of its contents is trusted at a lower bar

```python
# [PALAIS-FIX] For thin tier with sparse Wikidata: restore GPT candidates
if _verification_tier == 'thin' and len(poi_list) < 3 and len(_pre_d1v2_candidates) >= 3:
    _verified_names = set(p['name'].lower() for p in poi_list)
    _unverified = [p for p in _pre_d1v2_candidates if p['name'].lower() not in _verified_names]
    poi_list = list(poi_list) + _unverified[:5]
```

### Fix 2: R4 thin-tier handling

For `thin` tier with < 3 verified works, set `total_stops = min(requested, 5)` instead of capping to the 1 verified work. This allows the pipeline to produce a meaningful tour.

```python
if _verification_tier == 'thin' and len(poi_list) < 3:
    _thin_cap = min(total_stops, 5)
    total_stops = _thin_cap
```

### Fix 3: BLOCKER1 threshold fix

Changed from `suspect_venues >= len(poi_list) // 2` (which is 0 for a 1-item list — always true) to `suspect_venues >= max(1, len(poi_list) // 2)` (requires at least 1 actual suspect venue).

```python
if len(_suspect_venues) >= max(1, len(poi_list) // 2):
```

## Verification

After deploying the fix, the same request succeeds:
- `"Palais Lascaris, Nice, France"` → **10,425 chars generated**, 6 stops including The Holy Family, The Annunciation, etc.
- The thin-tier degraded mode fires: "THIN tier degraded mode: restoring 6 GPT candidates (Wikidata catalog too sparse for strict filtering)"

## Risk Assessment

**Scope:** Only affects museums with `tier=thin` (1-2 works in Wikidata) where GPT proposes ≥ 3 candidates. Major museums (rich/medium tier) are unaffected.

**Tradeoff:** Thin-tier tours may include works GPT believes exist but that can't be verified against Wikidata. This is acceptable because:
1. The venue itself IS Wikidata-verified (it's a real museum)
2. GPT has strong knowledge of well-known museums' contents
3. A degraded tour with possibly-imprecise work names is better than refusing to generate anything
4. The QA layer (BLOCKER4c) still runs and catches factual errors

**No regression:** The fix only fires when `tier=thin AND len(verified) < 3 AND len(gpt_candidates) >= 3`. Museums with good Wikidata coverage are unaffected.
