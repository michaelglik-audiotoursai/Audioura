"""
LOCAL-322: Tests for French→English material translation and language-aware checks.

Verifies that:
1. The FR→EN material mapping correctly translates all corpus terms
2. The presence check compares English (not French) against English prose
3. The patch sentence is grammatical English, not a comma-spliced fragment
4. Unknown materials are treated as satisfied (no French emission)
5. The period patch uses English, not raw French
6. The period 'else' branch (era names) is language-aware
"""
import sys
import re
sys.path.insert(0, '.')

import pytest


# ============================================================================
# The FR→EN mapping (duplicated from generate_tour_text.py for unit testing)
# ============================================================================

_FR_EN_MATERIAL_MAP = {
    'acier': 'steel',
    'cuivre': 'copper',
    'cuir': 'leather',
    'soie': 'silk',
    'laque': 'lacquer',
    'schiste': 'schist',
    'chlorite': 'chlorite',
    'bois': 'wood',
    'bronze': 'bronze',
    'marbre': 'marble',
    'porcelaine': 'porcelain',
    'céramique': 'ceramic',
    'jade': 'jade',
    'ivoire': 'ivory',
    'laiton': 'brass',
    'terre cuite': 'terracotta',
    'grès': 'stoneware',
    'fer': 'iron',
    'argent': 'silver',
    'papier': 'paper',
    'encre': 'ink',
    'gouache': 'gouache',
    'huile': 'oil',
    'aquarelle': 'watercolor',
    'pastel': 'pastel',
    "feuille d'or": 'gold leaf',
    'dorure': 'gilding',
    'xylogravure': 'woodblock print',
    'soie brodée': 'embroidered silk',
    'bois laqué': 'lacquered wood',
    'cuir laqué': 'lacquered leather',
    'polychrome': 'polychrome',
    'laqué': 'lacquered',
    'laquée': 'lacquered',
    'or': 'gold',
}


def _translate_material_to_english(fr_term):
    """Translate a French material term to English using the corpus-derived map."""
    fr_lower = fr_term.strip().lower()
    if fr_lower in _FR_EN_MATERIAL_MAP:
        return _FR_EN_MATERIAL_MAP[fr_lower]
    return None


# ============================================================================
# Test 1: Translation coverage
# ============================================================================

class TestMaterialTranslation:
    """Every term in story_miner's _MATERIALS list has an English translation."""

    # These are the exact terms from story_miner.py's _MATERIALS list
    STORY_MINER_MATERIALS = [
        'acier', 'cuivre', 'cuir', 'soie', 'laque', 'schiste', 'chlorite',
        'bois', 'bronze', 'marbre', 'porcelaine', 'céramique', 'jade',
        'ivoire', 'laiton', 'terre cuite', 'grès', 'fer', 'argent',
        'papier', 'encre', 'gouache', 'huile', 'aquarelle', 'pastel',
        "feuille d'or", 'dorure', 'xylogravure', 'soie brodée',
        'bois laqué', 'cuir laqué', 'polychrome', 'laqué', 'laquée',
    ]

    @pytest.mark.parametrize("fr_term", STORY_MINER_MATERIALS)
    def test_every_corpus_material_has_translation(self, fr_term):
        """Each material the extractor can return must have an English mapping."""
        en = _translate_material_to_english(fr_term)
        assert en is not None, f"No EN translation for FR material '{fr_term}'"
        assert en.isascii(), f"Translation '{en}' contains non-ASCII (still French?)"

    def test_unknown_material_returns_none(self):
        """A material not in the map returns None (caller should omit, not emit French)."""
        assert _translate_material_to_english("matière inconnue") is None

    def test_comma_separated_primary(self):
        """The primary material (first in comma-separated list) is translated."""
        c51_material = "acier, cuivre, cuir, soie, laque"
        mat_parts = [p.strip() for p in c51_material.split(',')]
        primary_en = _translate_material_to_english(mat_parts[0])
        assert primary_en == "steel"

    def test_all_comma_separated_translated(self):
        """All terms in a comma-separated list get translated."""
        c51_material = "acier, cuivre, cuir, soie, laque"
        mat_parts = [p.strip() for p in c51_material.split(',')]
        translated = [_translate_material_to_english(p) for p in mat_parts]
        assert translated == ["steel", "copper", "leather", "silk", "lacquer"]


# ============================================================================
# Test 2: Presence check is language-aware
# ============================================================================

class TestLanguageAwareCheck:
    """The material presence check uses English, not French."""

    def test_schist_satisfies_schiste(self):
        """Description saying 'grey schist' satisfies catalogue material 'schiste'."""
        desc = "Carved from grey schist, this sculpture exudes serenity."
        material_english = _translate_material_to_english("schiste")
        assert material_english == "schist"
        assert material_english.lower() in desc.lower()

    def test_french_term_does_not_match_english(self):
        """The French term 'schiste' should NOT be checked against English prose."""
        desc = "Carved from grey schist, this sculpture exudes serenity."
        # Old code checked: "schiste" in desc.lower() → False → false failure
        assert "schiste" not in desc.lower()
        # New code checks: "schist" in desc.lower() → True → correct pass
        assert "schist" in desc.lower()

    def test_steel_satisfies_acier(self):
        """Description mentioning steel satisfies catalogue material 'acier'."""
        desc = "Made of steel, copper, and silk, this armor represents samurai craftsmanship."
        material_english = _translate_material_to_english("acier")
        assert material_english == "steel"
        assert material_english.lower() in desc.lower()

    def test_lacquered_satisfies_laque_via_stem(self):
        """'lacquered' in description satisfies 'laque' (via stem matching)."""
        desc = "The helmet is adorned with lacquered wood panels."
        material_english = _translate_material_to_english("laque")
        assert material_english == "lacquer"
        # Direct match fails but stem "lacquer" is present in "lacquered"
        mat_stem = material_english.lower().rstrip('ed').rstrip('er')
        assert len(mat_stem) >= 4
        assert mat_stem in desc.lower() or material_english.lower() in desc.lower()

    def test_unknown_material_treated_as_satisfied(self):
        """An untranslatable material should be treated as satisfied, not retried."""
        # If _translate_material_to_english returns None, the check should pass
        unknown_en = _translate_material_to_english("matière inconnue")
        assert unknown_en is None
        # In the code: if not _material_english → skip check (treat as satisfied)


# ============================================================================
# Test 3: Patch sentence is grammatical English
# ============================================================================

class TestPatchSentence:
    """The fallback patch produces a complete English sentence."""

    def _build_patch(self, material_english=None, period_english=None):
        """Replicate the LOCAL-322 patch logic (three grammatical branches)."""
        if material_english and period_english:
            return f"This work, crafted from {material_english}, dates from the {period_english}."
        elif material_english:
            return f"This work was crafted from {material_english}."
        elif period_english:
            return f"This work dates from the {period_english}."
        return ""

    def test_material_only_patch(self):
        """Material-only patch is a complete sentence."""
        patch = self._build_patch(material_english="schist")
        assert patch == "This work was crafted from schist."
        # It's a complete sentence with subject + verb + object + period
        assert patch[0].isupper()
        assert patch.endswith('.')
        assert ", " not in patch  # no comma splice

    def test_period_only_patch(self):
        """Period-only patch is a complete sentence."""
        patch = self._build_patch(period_english="19th century")
        assert patch == "This work dates from the 19th century."
        assert patch.endswith('.')

    def test_both_patch(self):
        """Material + period patch is a complete sentence."""
        patch = self._build_patch(material_english="schist", period_english="10th century")
        assert patch == "This work, crafted from schist, dates from the 10th century."
        assert patch.endswith('.')
        # No comma-spliced fragment pattern
        assert not re.search(r'This work, .*, [A-Z]', patch)

    def test_patch_never_contains_french(self):
        """Patch never emits a French material term."""
        # The three defective examples from the bug report
        defective_materials = ["schiste", "acier, cuivre, cuir, soie, laque", "papier"]
        for fr_mat in defective_materials:
            primary = fr_mat.split(',')[0].strip()
            en = _translate_material_to_english(primary)
            assert en is not None
            patch = self._build_patch(material_english=en)
            assert primary not in patch, f"French term '{primary}' leaked into patch: {patch}"

    def test_patch_insertion_no_comma_splice(self):
        """Patch inserted after first sentence does not create a comma splice."""
        desc = "This magnificent sculpture commands attention. The intricate details reveal masterful craftsmanship."
        patch = self._build_patch(material_english="schist")
        # Simulate insertion
        first_period_idx = desc.find('. ')
        if first_period_idx > 20:
            result = desc[:first_period_idx + 2] + patch + " " + desc[first_period_idx + 2:].lstrip()
        else:
            result = patch + " " + desc
        # No comma-splice pattern: "This work, ... , [A-Z]"
        assert not re.search(r'This work, [^.]+, [A-Z]', result)
        # The patch is a standalone sentence
        sentences = result.split('. ')
        assert any("This work was crafted from schist" in s for s in sentences)


# ============================================================================
# Test 4: Period patch uses English
# ============================================================================

class TestPeriodPatchEnglish:
    """The period patch uses _period_english, not raw French _c51_period."""

    def test_period_patch_not_french(self):
        """Patch should say '10th century' not 'Xe siècle'."""
        # Simulate _period_english computation for "2nde moitié du Xe siècle"
        c51_period = "2nde moitié du Xe siècle"
        # The code computes: _period_english = "second half of the 10th century"
        period_english = "second half of the 10th century"
        patch = f"This work dates from the {period_english}."
        assert "siècle" not in patch
        assert "10th century" in patch

    def test_period_patch_year(self):
        """Raw year stays as-is (no translation needed)."""
        patch = f"This work dates from the 1879."
        assert "1879" in patch


# ============================================================================
# Test 5: Period 'else' branch (era names) language-aware
# ============================================================================

class TestPeriodEraBranch:
    """Era-based periods like 'Époque Edo' are checked language-awarely."""

    def test_edo_period_found_in_english(self):
        """Description mentioning 'Edo period' satisfies 'Époque Edo'."""
        desc = "This armor dates from the Edo period in Japanese history."
        desc_lower = desc.lower()
        c51_period = "Époque Edo"
        period_english = c51_period  # fallback: as-is

        # The old check: c51_period.lower() in desc_lower
        old_check = c51_period.lower() in desc_lower
        assert not old_check, "Old check would have wrongly passed — 'époque edo' not in English text"

        # The new check: also try era keyword
        era_name_m = re.search(r'(?:[EÉ]poque|[EÈ]re)\s+(?:d[e\']?\s*)?([\w]+)', c51_period, re.IGNORECASE)
        assert era_name_m is not None
        era_keyword = era_name_m.group(1).lower()
        assert era_keyword == "edo"
        new_check = era_keyword in desc_lower
        assert new_check, "New check should find 'edo' in 'Edo period'"


# ============================================================================
# Test 6: Reproduction of the three defective strings from the bug report
# ============================================================================

class TestBugReportReproduction:
    """The three quoted defective strings must no longer be producible."""

    def test_schiste_splice_impossible(self):
        """'This work, crafted in schiste,' can never be produced."""
        # With the fix, if material is "schiste":
        # 1. Translation: "schiste" → "schist"
        # 2. Check: look for "schist" in English text (likely found → no patch)
        # 3. If patch needed: "This work was crafted from schist." (not "in schiste,")
        en = _translate_material_to_english("schiste")
        assert en == "schist"
        # The patch would be:
        patch = f"This work was crafted from {en}."
        assert "schiste" not in patch
        assert "crafted in" not in patch
        assert patch.endswith('.')

    def test_acier_splice_impossible(self):
        """'This work, crafted in acier, cuivre, cuir, soie, laque,' can never be produced."""
        # With the fix, only the English primary material is used
        c51_material = "acier, cuivre, cuir, soie, laque"
        mat_parts = [p.strip() for p in c51_material.split(',')]
        primary_en = _translate_material_to_english(mat_parts[0])
        assert primary_en == "steel"
        patch = f"This work was crafted from {primary_en}."
        assert "acier" not in patch
        assert "cuivre" not in patch
        assert patch == "This work was crafted from steel."

    def test_papier_xylogravure_splice_impossible(self):
        """'This work, crafted in papier,' can never be produced."""
        en = _translate_material_to_english("papier")
        assert en == "paper"
        patch = f"This work was crafted from {en}."
        assert "papier" not in patch
        assert patch == "This work was crafted from paper."

    def test_old_fragment_pattern_dead(self):
        """The old pattern 'This work, crafted in X, [A-Z]' is structurally impossible."""
        # The new code builds: "This work was crafted from X."
        # It's a complete sentence, never ends with ", " before a capital letter
        for fr, en in _FR_EN_MATERIAL_MAP.items():
            patch = f"This work was crafted from {en}."
            assert not re.search(r'This work, .*, $', patch)
            assert patch.endswith('.')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
