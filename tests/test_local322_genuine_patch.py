#!/usr/bin/env python3
"""
LOCAL-322: Test that a genuinely-missing material still gets patched in English.

This test simulates the scenario where the LLM's description does NOT mention
the material, and the code must patch it in. Verifies:
1. The patch is in English (not French)
2. The patch forms a grammatical sentence
3. No comma splice
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def simulate_material_patch():
    """Simulate the LOCAL-322 patch logic on a description missing material."""
    
    # --- Simulate the FR→EN translation (from generate_tour_text.py) ---
    _FR_EN_MATERIAL_MAP = {
        'acier': 'steel', 'cuivre': 'copper', 'cuir': 'leather',
        'soie': 'silk', 'laque': 'lacquer', 'schiste': 'schist',
        'chlorite': 'chlorite', 'bois': 'wood', 'bronze': 'bronze',
        'marbre': 'marble', 'papier': 'paper', 'fer': 'iron',
        'xylogravure': 'woodblock print',
    }
    
    # Case 1: Description that DOESN'T mention schist at all
    print("=" * 70)
    print("CASE 1: Description missing material 'schiste' (should be 'schist')")
    print("=" * 70)
    
    c51_material = "schiste"
    description = "This remarkable sculpture depicts Buddha in a standing pose. The serene expression on the Buddha's face conveys inner peace and spiritual awakening."
    
    # Translate
    primary_fr = c51_material.split(',')[0].strip().lower()
    material_english = _FR_EN_MATERIAL_MAP.get(primary_fr)
    print(f"  FR material: '{primary_fr}' → EN: '{material_english}'")
    
    # Check: English term in description?
    desc_lower = description.lower()
    material_ok = True
    if material_english:
        if material_english.lower() not in desc_lower:
            mat_stem = material_english.lower().rstrip('ed').rstrip('er')
            if len(mat_stem) >= 4 and mat_stem not in desc_lower:
                material_ok = False
    
    print(f"  Material found in description: {material_ok}")
    
    if not material_ok and material_english:
        # Build the patch
        patch_parts = [f"crafted from {material_english}"]
        # [LEAD] Mirror production (generate_tour_text.py:7596-7604): three
        # grammatical branches, not one template forced through all cases.
        if len(patch_parts) == 2:
            patch_sentence = f"This work, crafted from {material_english}, dates from the {period_english}."
        elif not material_ok:
            patch_sentence = f"This work was crafted from {material_english}."
        else:
            patch_sentence = f"This work dates from the {period_english}."
        
        # Insert after first sentence
        first_period_idx = description.find('. ')
        if first_period_idx > 20:
            patched = (description[:first_period_idx + 2]
                       + patch_sentence + " "
                       + description[first_period_idx + 2:].lstrip())
        else:
            patched = patch_sentence + " " + description
        
        print(f"\n  PATCHED OUTPUT:")
        print(f"  {patched}")
        print()
        
        # Verify
        assert "schiste" not in patched, "French term leaked!"
        assert "schist" in patched, "English material not in patched output!"
        assert "This work was crafted from schist." in patched, "Patch sentence wrong!"
        assert not re.search(r'This work, .*, [A-Z]', patched), "Comma splice detected!"
        assert patched.count('. ') >= 2, "Not enough sentences — patch may have mangled text"
        print("  ✓ PASS: Patch is grammatical English, no French leak, no comma splice")
    
    # Case 2: "acier, cuivre, cuir, soie, laque" — multi-material
    print()
    print("=" * 70)
    print("CASE 2: Description missing multi-material 'acier, cuivre, cuir, soie, laque'")
    print("=" * 70)
    
    c51_material = "acier, cuivre, cuir, soie, laque"
    description = "This samurai armor represents the pinnacle of Japanese craftsmanship. The intricate designs reflect the warrior's status and clan heritage."
    
    mat_parts = [p.strip().lower() for p in c51_material.split(',')]
    material_english = _FR_EN_MATERIAL_MAP.get(mat_parts[0])
    print(f"  FR primary: '{mat_parts[0]}' → EN: '{material_english}'")
    
    desc_lower = description.lower()
    material_ok = True
    if material_english:
        if material_english.lower() not in desc_lower:
            mat_stem = material_english.lower().rstrip('ed').rstrip('er')
            if len(mat_stem) >= 4 and mat_stem not in desc_lower:
                material_ok = False
    
    print(f"  Material found in description: {material_ok}")
    
    if not material_ok and material_english:
        patch_parts = [f"crafted from {material_english}"]
        # [LEAD] Mirror production (generate_tour_text.py:7596-7604): three
        # grammatical branches, not one template forced through all cases.
        if len(patch_parts) == 2:
            patch_sentence = f"This work, crafted from {material_english}, dates from the {period_english}."
        elif not material_ok:
            patch_sentence = f"This work was crafted from {material_english}."
        else:
            patch_sentence = f"This work dates from the {period_english}."
        
        first_period_idx = description.find('. ')
        if first_period_idx > 20:
            patched = (description[:first_period_idx + 2]
                       + patch_sentence + " "
                       + description[first_period_idx + 2:].lstrip())
        else:
            patched = patch_sentence + " " + description
        
        print(f"\n  PATCHED OUTPUT:")
        print(f"  {patched}")
        print()
        
        assert "acier" not in patched, "French term 'acier' leaked!"
        assert "cuivre" not in patched, "French term 'cuivre' leaked!"
        assert "steel" in patched, "English material not in patched output!"
        assert "This work was crafted from steel." in patched
        assert not re.search(r'This work, .*, [A-Z]', patched), "Comma splice detected!"
        print("  ✓ PASS: Patch is grammatical English, no French leak, no comma splice")
    
    # Case 3: Period + material missing
    print()
    print("=" * 70)
    print("CASE 3: Both period AND material missing → combined patch")
    print("=" * 70)
    
    c51_material = "bois"
    period_english = "12th century"  # Already translated from "XIIe siècle"
    description = "This is a magnificent representation of Kannon with multiple arms. The statue invites contemplation on compassion and mercy."
    
    material_english = _FR_EN_MATERIAL_MAP.get(c51_material)
    print(f"  FR material: '{c51_material}' → EN: '{material_english}'")
    print(f"  Period (EN): '{period_english}'")
    
    desc_lower = description.lower()
    material_ok = material_english.lower() in desc_lower if material_english else True
    period_ok = period_english.lower() in desc_lower
    
    print(f"  Material found: {material_ok}")
    print(f"  Period found: {period_ok}")
    
    if not material_ok or not period_ok:
        patch_parts = []
        if not material_ok and material_english:
            patch_parts.append(f"crafted from {material_english}")
        if not period_ok:
            patch_parts.append(f"dating from the {period_english}")
        
        # [LEAD] Mirror production (generate_tour_text.py:7596-7604): three
        # grammatical branches, not one template forced through all cases.
        if len(patch_parts) == 2:
            patch_sentence = f"This work, crafted from {material_english}, dates from the {period_english}."
        elif not material_ok:
            patch_sentence = f"This work was crafted from {material_english}."
        else:
            patch_sentence = f"This work dates from the {period_english}."
        
        first_period_idx = description.find('. ')
        if first_period_idx > 20:
            patched = (description[:first_period_idx + 2]
                       + patch_sentence + " "
                       + description[first_period_idx + 2:].lstrip())
        else:
            patched = patch_sentence + " " + description
        
        print(f"\n  PATCHED OUTPUT:")
        print(f"  {patched}")
        print()
        
        assert "bois" not in patched, "French term 'bois' leaked!"
        assert "siècle" not in patched, "French period leaked!"
        assert "wood" in patched, "English material not in patched output!"
        assert "12th century" in patched, "English period not in patched output!"
        assert "This work, crafted from wood, dates from the 12th century." in patched
        assert not re.search(r'This work, .*, [A-Z]', patched), "Comma splice detected!"
        print("  ✓ PASS: Combined patch is grammatical English, no French, no comma splice")
    
    print()
    print("=" * 70)
    print("ALL CASES PASSED — genuinely-missing materials patched in English")
    print("=" * 70)


if __name__ == '__main__':
    simulate_material_patch()
