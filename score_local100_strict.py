#!/usr/bin/env python3
"""
LOCAL-100 scoring — STRICT callback interpretation.
Only counts genuine narrative callbacks in body text.
Excludes: epilog/wrap-up lines, Directions lines, shared-subject coincidences.
"""
import sys, re, os
sys.path.insert(0, '.')

N = 8
SHARE = 100.0 / N  # 12.5

# Classification weights
WEIGHTS = {'FABRICATED': -1.0, 'MISSING': -1.0, 'THIN': 0.5, 'ADEQUATE': 0.75, 'RICH': 1.0}

# ============================================================
# MANUAL CLASSIFICATIONS — based on reading every stop in full
# ============================================================

classifications = {
    1: {
        1: "RICH",    # steel, silk, gold leaf, lacquer, 19th century — 5 catalogue materials
        2: "ADEQUATE",# grey schist, 3rd century (close to 2nd), Greco-Buddhist
        3: "RICH",    # chlorite, 10th century, Bengale region — 3 catalogue facts
        4: "RICH",    # cypress wood, 12th century, 11 heads, lotus, pierced mandorla — 5 facts
        5: "RICH",    # woodblock print, 1879, Chikanobu — 3 catalogue facts
        6: "ADEQUATE",# jiangyi, silk, 18th century — 2-3 facts, mostly generic symbolism
        7: "THIN",    # No material, no date, no provenance. Only iconographic.
        8: "ADEQUATE",# 16th century, lacquered wood, Noh/kojô — 3 facts
    },
    2: {
        1: "RICH",    # acier/cuivre/cuir/soie/laque/feuille d'or — all 6 materials listed
        2: "RICH",    # grey schist, 2nd century, Pakistan — 3 catalogue facts  
        3: "RICH",    # chlorite, 10th century, Pala dynasty/Bengal — 3 facts
        4: "RICH",    # cypress wood, 12th century, Juichimen, 11 heads, lotus, mandorla
        5: "RICH",    # woodblock print, 1879, Chikanobu, polychrome on paper
        6: "ADEQUATE",# soie, 18th century. No jiangyi. Generic prose.
        7: "THIN",    # bronze (unconfirmed), no date, no provenance. 33% filler.
        8: "ADEQUATE",# wood, Noh/kojô. No date.
    },
    3: {
        1: "RICH",    # lacquer, silk, gold leaf, 19th century, samurai dô-maru
        2: "ADEQUATE",# grey schist, 2nd century, Greco-Buddhist. 33% filler.
        3: "ADEQUATE",# chlorite (×2), 10th century. No Bengal provenance. 2 facts.
        4: "RICH",    # Juichimen, 11 heads, 12th century, lotus, mandorla, bois. 4+ facts.
        5: "RICH",    # Chikanobu, xylogravure, 1879, papier. 3 facts.
        6: "ADEQUATE",# jiangyi, soie, 18th century, embroidery. 3 facts.
        7: "THIN",    # No material, no date, no provenance. 36% filler.
        8: "ADEQUATE",# lacquer, wood, Noh/kojô. No 16th century date stated.
    },
    4: {
        1: "RICH",    # steel/copper/leather/silk/lacquer/gold leaf — all 6 materials, 1850
        2: "ADEQUATE",# schiste, 3rd century (close), Pakistan, Hellenistic. 2-3 facts.
        3: "RICH",    # chlorite, 10th century, Bengale — 3 facts
        4: "RICH",    # cypress wood, 12th century, 11 heads. Multiple facts.
        5: "RICH",    # Chikanobu, xylogravure polychrome papier, 1879. 3 facts.
        6: "ADEQUATE",# jiangyi, soie, 18th century. Short but 2 facts.
        7: "THIN",    # No material, no date. 38% filler.
        8: "ADEQUATE",# 16th century, wood, lacquer, Noh, kojô. 3 facts.
    },
    5: {
        1: "RICH",    # steel, silk, lacquer, gold leaf, 19th century, Edo, dô-maru
        2: "ADEQUATE",# grey schist, 3rd century (off by 1). 2 facts.
        3: "ADEQUATE",# chlorite, 10th century. No Bengal. 2 facts.
        4: "RICH",    # cypress wood, 12th century, Juichimen, 11 heads, lotus, mandorla
        5: "RICH",    # Toyohara Chikanobu (full name!), xylogravure, 1879
        6: "ADEQUATE",# soie, 18th century, embroidery. No jiangyi. 2 facts.
        7: "THIN",    # No material, no date. 30% filler.
        8: "ADEQUATE",# wood, lacquer, Noh/kojô. No date.
    },
}

# ============================================================
# GENUINE CALLBACKS — manually verified by reading body text
# ============================================================
# Rules applied:
#   - Must be in body text (not Directions, not epilog)
#   - Must reference SPECIFIC CONTENT from another stop (not just shared subject)
#   - Exclude: templated wrap-up ("From X through Y to Z")
#   - Exclude: shared-subject coincidence (both Kannon stops share words naturally)

genuine_callbacks = {
    1: {
        # Stop 4 body: "Just as La danse cosmique de Ganesh embodies the joy of creation"
        4: [3],
        # Stop 8 body: "resonating with other works like the 'Kannon à mille bras'"
        8: [7],
    },
    2: {
        # Stop 1 body mentions "Kannon" in the intro paragraph — but checking...
        # Actually the intro for Stop 1 in Run 2 mentions "harmonious fusion of Japanese armor...
        # cosmic dance of Ganesh...serene presence of Buddha...compassionate gaze of Kannon"
        # This is an introductory narrative setup, not a genuine callback from stop to stop.
        # Stop 8 body: mentions "Andô Naoyuki" and "Ulysses Grant" but in epilog line. 
        # No genuine body callbacks in Run 2.
    },
    3: {
        # Stop 2 body: mentions "L'Armure d'Andô Naoyuki" — checking...
        # Run3 Stop 2: "The museum's collection, including works like L'Armure d'Andô Naoyuki" 
        # — this is genuine callback from Stop 2 to Stop 1
        2: [1],
        # Stop 7: refs Stop 4 — but this is just Kannon subject matter overlap, not callback
    },
    4: {
        # Stop 3 body: "consider the connection between 'La danse cosmique de Ganesh' and 
        # the earlier stop at 'Statue de Bouddha'" — GENUINE callback
        3: [2],
        # Stop 4 body: "Just as La danse cosmique de Ganesh showcased the dynamic energy" — GENUINE
        4: [3],
    },
    5: {
        # Stop 8 body: "From Statue de Bouddha to Masque du vieillard kojô, you have followed..."
        # — this is epilog/wrap-up line, NOT a genuine callback.
        # No genuine body-text callbacks in Run 5.
    },
}

# ============================================================
# VENUE IDENTITY FACTS
# ============================================================
venue_identity_per_run = {
    1: ['architect_named', 'founding_date'],                              # 2/5
    2: ['architect_named', 'founding_date', 'exact_founding_date'],       # 3/5
    3: ['architect_named', 'founding_date', 'exact_founding_date'],       # 3/5
    4: ['architect_named', 'founding_date', 'exact_founding_date', 'founder/donor_named'],  # 4/5
    5: ['architect_named', 'founding_date', 'exact_founding_date', 'founder/donor_named'],  # 4/5
}

# ============================================================
# COMPUTE SCORES
# ============================================================

print(f"{'='*70}")
print(f"  LOCAL-100 SCORING — STRICT INTERPRETATION")
print(f"  N=8, share={SHARE:.2f}")
print(f"{'='*70}")

all_scores = []

for run_num in range(1, 6):
    # Base score
    base = 0.0
    per_stop_base = []
    for stop_idx in range(1, 9):
        cls = classifications[run_num][stop_idx]
        b = WEIGHTS[cls] * SHARE
        per_stop_base.append(b)
        base += b
    
    # Structural surcharge (none in any run — no false attributions, no template placeholders)
    structural = 0.0
    
    # Correlation bonus — STRICT: only genuine callbacks
    callbacks = genuine_callbacks.get(run_num, {})
    affected_stops = set()
    for stop_idx, refs in callbacks.items():
        affected_stops.add(stop_idx)
        affected_stops.update(refs)
    
    affected_value = 0.0
    for stop_idx in affected_stops:
        affected_value += per_stop_base[stop_idx - 1]
    correlation_bonus = 0.5 * affected_value
    
    # Venue identity bonus: up to 10% of base, scaled by facts/5
    vi_facts = venue_identity_per_run[run_num]
    identity_fraction = min(len(vi_facts), 5) / 5.0
    venue_bonus = 0.10 * base * identity_fraction
    
    total = base + structural + correlation_bonus + venue_bonus
    all_scores.append(total)
    
    print(f"\n  RUN {run_num}:")
    print(f"    Per-stop: ", end="")
    for i, cls in enumerate(classifications[run_num].values()):
        print(f"S{i+1}={cls[0]}", end=" ")
    print()
    print(f"    Base:          {base:+.2f}")
    print(f"    Structural:    {structural:+.2f}")
    print(f"    Correlation:   {correlation_bonus:+.2f} (affected: {sorted(affected_stops) if affected_stops else 'none'})")
    print(f"    Venue ID:      {venue_bonus:+.2f} ({len(vi_facts)}/5 facts)")
    print(f"    ─────────────────────────")
    print(f"    TOTAL:         {total:.1f}")

# Summary
print(f"\n{'='*70}")
print(f"  SUMMARY")
print(f"{'='*70}")
mean = sum(all_scores) / len(all_scores)
spread = max(all_scores) - min(all_scores)
print(f"\n  Scores: {[f'{s:.1f}' for s in all_scores]}")
print(f"  Mean:   {mean:.1f}")
print(f"  Spread: {spread:.1f}")
print(f"  Min:    {min(all_scores):.1f}  Max: {max(all_scores):.1f}")
print(f"\n  *** Gate (≥75): {'YES ✓' if mean >= 75.0 else 'NO ✗'} ***")

# Fact coverage
print(f"\n  Fact coverage (D27 settlement):")
for run_num in range(1, 6):
    cls = classifications[run_num]
    carrying = sum(1 for v in cls.values() if v in ('RICH', 'ADEQUATE'))
    rich = sum(1 for v in cls.values() if v == 'RICH')
    thin = sum(1 for v in cls.values() if v == 'THIN')
    print(f"    Run {run_num}: {carrying}/8 carry catalogue facts  (RICH={rich}, ADEQUATE={carrying-rich}, THIN={thin})")

# Cost
costs = [0.0669, 0.0700, 0.0673, 0.0672, 0.0698]
total_cost = sum(costs)
print(f"\n  Cost per run: {['$'+f'{c:.4f}' for c in costs]}")
print(f"  Total cost:   ${total_cost:.4f}")
print(f"  Mean cost:    ${total_cost/5:.4f}")
print(f"  All under $1.30: YES ✓ (max ${max(costs):.4f})")
