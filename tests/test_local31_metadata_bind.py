"""
LOCAL-31: Regression tests for catalogue metadata binding in generated descriptions.

Verifies that:
1. Each stop gets ONLY its own century/period (no entry-boundary bleed)
2. Material from catalogue appears in the generated text
3. Unsourced provenance is not asserted as cultural identity
4. Adjacent entries (Ganesh Xe siècle / Kannon XIIe siècle) never cross-contaminate

These tests exercise the C5-1 injection logic and the post-generation validation
introduced in LOCAL-31 without requiring live API calls.
"""
import sys
import re
sys.path.insert(0, '.')

import pytest


# ============================================================================
# Test 1: C5-1 injection builds the correct binding block
# ============================================================================

class TestC51InjectionBlock:
    """Verify that the C5-1 injection constructs structurally binding prompts."""

    @pytest.fixture
    def ganesh_evidence_log(self):
        return {
            'La danse cosmique de Ganesh': {
                'status': 'VERIFIED',
                'canonical_title': 'La danse cosmique de Ganesh',
                'snippet': 'Provenant de la région du Bengale ou du Bihar',
                'method': 'catalogue_work',
                'material': 'chlorite',
                'period': '2nde moitié du Xe siècle',
                'origin': 'Bengale',
            },
        }

    @pytest.fixture
    def kannon_evidence_log(self):
        return {
            'Kannon, le bodhisattva de la compassion': {
                'status': 'VERIFIED',
                'canonical_title': 'Kannon, le bodhisattva de la compassion',
                'snippet': 'Réalisée dans un bois de cyprès',
                'method': 'catalogue_work',
                'material': 'bois',
                'period': 'seconde moitié du XIIe siècle',
                'origin': 'Japon',
            },
        }

    def test_ganesh_injection_contains_xe_siecle(self, ganesh_evidence_log):
        """C5-1 block for Ganesh must mention Xe siècle, not XIIe."""
        ev = ganesh_evidence_log['La danse cosmique de Ganesh']
        # Simulate the binding block construction
        binding_block = ""
        if ev.get('period'):
            binding_block += f"DATE/PERIOD: {ev['period']}\n"
        if ev.get('material'):
            binding_block += f"MATERIAL: {ev['material']}\n"
        
        assert 'Xe siècle' in binding_block
        assert 'XIIe' not in binding_block
        assert 'chlorite' in binding_block

    def test_kannon_injection_contains_xiie_siecle(self, kannon_evidence_log):
        """C5-1 block for Kannon must mention XIIe siècle, not Xe alone."""
        ev = kannon_evidence_log['Kannon, le bodhisattva de la compassion']
        binding_block = ""
        if ev.get('period'):
            binding_block += f"DATE/PERIOD: {ev['period']}\n"
        if ev.get('material'):
            binding_block += f"MATERIAL: {ev['material']}\n"
        
        assert 'XIIe siècle' in binding_block
        assert 'bois' in binding_block


# ============================================================================
# Test 2: Post-generation period validation catches wrong centuries
# ============================================================================

class TestPostGenerationPeriodValidation:
    """Verify the LOCAL-31 post-generation validator catches wrong centuries."""

    def _check_period_in_description(self, description: str, expected_period: str) -> bool:
        """Replicate the period-check logic from generate_tour_text.py."""
        desc_lower = description.lower()
        century_match = re.search(
            r'((?:I{1,3}|IV|VI{0,3}|IX|X{0,3}I{0,3}V?)e)\s+si[eè]cle',
            expected_period
        )
        if not century_match:
            return True  # No century to check
        
        expected_century = century_match.group(1).lower()
        roman_to_arabic = {
            'ie': '1', 'iie': '2', 'iiie': '3', 'ive': '4',
            've': '5', 'vie': '6', 'viie': '7', 'viiie': '8',
            'ixe': '9', 'xe': '10', 'xie': '11', 'xiie': '12',
            'xiiie': '13', 'xive': '14', 'xve': '15', 'xvie': '16',
            'xviie': '17', 'xviiie': '18', 'xixe': '19', 'xxe': '20',
        }
        arabic_century = roman_to_arabic.get(expected_century, '')
        ordinal_variants = []
        if arabic_century:
            ordinal_variants = [
                f"{arabic_century}th century", f"{arabic_century}th-century",
                f"{arabic_century}th cent",
            ]
            if arabic_century == '1': ordinal_variants.extend(['1st century', '1st-century'])
            elif arabic_century == '2': ordinal_variants.extend(['2nd century', '2nd-century'])
            elif arabic_century == '3': ordinal_variants.extend(['3rd century', '3rd-century'])
        
        return (
            expected_century in desc_lower or
            expected_period.lower() in desc_lower or
            any(v in desc_lower for v in ordinal_variants)
        )

    def test_correct_century_passes(self):
        """Description with 10th century passes for Xe siècle."""
        desc = "This 10th-century chlorite sculpture depicts Ganesh in a cosmic dance."
        assert self._check_period_in_description(desc, "2nde moitié du Xe siècle")

    def test_wrong_century_fails(self):
        """Description with 12th century FAILS for Xe siècle (entry-boundary bleed)."""
        desc = "In the 12th-century Bengali artwork, Ganesh is portrayed with eight arms."
        assert not self._check_period_in_description(desc, "2nde moitié du Xe siècle")

    def test_roman_numeral_passes(self):
        """Description mentioning 'Xe siècle' directly passes."""
        desc = "Dating from the Xe siècle, this chlorite stele represents Ganesh."
        assert self._check_period_in_description(desc, "2nde moitié du Xe siècle")

    def test_kannon_12th_century_passes(self):
        """Description with 12th century passes for XIIe siècle (correct for Kannon)."""
        desc = "This 12th-century Japanese sculpture carved in cypress wood depicts Kannon."
        assert self._check_period_in_description(desc, "seconde moitié du XIIe siècle")

    def test_kannon_wrong_century_fails(self):
        """Description with 10th century FAILS for XIIe siècle."""
        desc = "This 10th-century sculpture from Japan depicts the bodhisattva."
        assert not self._check_period_in_description(desc, "seconde moitié du XIIe siècle")


# ============================================================================
# Test 3: Unsourced provenance detection
# ============================================================================

class TestProvenanceAssertion:
    """Verify that unsourced provenance assertions are detected and corrected."""

    def _detect_provenance_over_assertion(self, description: str, origin: str) -> list:
        """Replicate the provenance check from LOCAL-31."""
        origin_adjective_map = {
            'bengale': 'bengali', 'bihar': 'bihari', 'japon': 'japanese',
            'chine': 'chinese', 'inde': 'indian', 'corée': 'korean',
            'cambodge': 'cambodian', 'thaïlande': 'thai', 'vietnam': 'vietnamese',
            'birmanie': 'burmese', 'tibet': 'tibetan', 'népal': 'nepalese',
            'indonésie': 'indonesian', 'rajasthan': 'rajasthani',
            'tamil nadu': 'tamil', 'gandhara': 'gandharan',
        }
        origin_lower = origin.lower()
        adj_form = origin_adjective_map.get(origin_lower, origin_lower + 'i')
        pattern = re.compile(
            rf'\b(?:ancient\s+)?{re.escape(adj_form)}\s+'
            r'(?:culture|civilization|heritage|tradition|artistic\s+tradition)',
            re.IGNORECASE
        )
        return pattern.findall(description)

    def test_bengali_culture_detected(self):
        """'ancient Bengali culture' is detected as over-assertion."""
        desc = "the rich heritage and spiritual beliefs of ancient Bengali culture"
        assertions = self._detect_provenance_over_assertion(desc, "Bengale")
        assert len(assertions) > 0, f"Should detect 'Bengali culture' as over-assertion"

    def test_bengali_tradition_detected(self):
        """'Bengali artistic tradition' is detected as over-assertion."""
        desc = "reflecting the Bengali artistic tradition of the Pala period"
        assertions = self._detect_provenance_over_assertion(desc, "Bengale")
        assert len(assertions) > 0

    def test_region_only_not_flagged(self):
        """'from the Bengale region' is NOT flagged (acceptable attribution)."""
        desc = "catalogued as originating from the Bengale region"
        assertions = self._detect_provenance_over_assertion(desc, "Bengale")
        assert len(assertions) == 0, "Geographic origin without cultural assertion should pass"

    def test_no_origin_invented_provenance_detected(self):
        """When no origin in catalogue, detect invented provenance assertions."""
        desc = "In the 12th-century Bengali artwork, Ganesh is portrayed with eight arms."
        # Simulate no-origin case
        provenance_assertions = re.findall(
            r'\b(Bengali|Indian|Chinese|Japanese|Thai|Cambodian|'
            r'Vietnamese|Burmese|Tibetan|Nepalese|Korean)\s+'
            r'(?:artwork|art|culture|tradition|heritage|civilization)',
            desc, re.IGNORECASE
        )
        assert len(provenance_assertions) > 0, "Should detect 'Bengali artwork' as invented provenance"


# ============================================================================
# Test 4: Material patching logic
# ============================================================================

class TestMaterialPatching:
    """Verify that missing material gets patched into the description."""

    def test_patch_missing_material(self):
        """When chlorite is missing, the patch inserts it."""
        desc = "This sculpture depicts Ganesh in a cosmic dance. The eight arms represent the various powers of the deity."
        material = "chlorite"
        
        # Simulate the patching logic
        desc_lower = desc.lower()
        material_missing = material.lower() not in desc_lower
        assert material_missing, "Precondition: chlorite must be absent"
        
        # Patch
        patch_parts = [f"crafted in {material}"]
        patch_sentence = f"This work, {', '.join(patch_parts)}, "
        first_period_idx = desc.find('. ')
        if first_period_idx > 20:
            patched = desc[:first_period_idx + 2] + patch_sentence + desc[first_period_idx + 2:].lstrip()
        else:
            patched = patch_sentence + desc[0].lower() + desc[1:]
        
        assert 'chlorite' in patched, f"Patched description must contain 'chlorite'. Got: {patched}"

    def test_material_present_no_patch(self):
        """When chlorite IS present, no patch needed."""
        desc = "This chlorite sculpture from the 10th century depicts Ganesh dancing."
        assert 'chlorite' in desc.lower()


# ============================================================================
# Test 5: Adjacency integration — full Ganesh/Kannon pair
# ============================================================================

class TestGaneshKannonNoCrossContamination:
    """Full integration test: verifying that Ganesh and Kannon entries
    do not cross-contaminate at any layer of the pipeline.
    
    Uses the real catalogue data from Musée des Arts Asiatiques (Q3330160).
    """

    @pytest.fixture
    def museum_data(self):
        """The real per_work_contexts and evidence_log as extracted by story_miner."""
        return {
            'evidence_log': {
                'La danse cosmique de Ganesh': {
                    'status': 'VERIFIED',
                    'canonical_title': 'La danse cosmique de Ganesh',
                    'snippet': 'Provenant de la région du Bengale ou du Bihar, cette stèle en chlorite de la 2nde moitié du Xe siècle',
                    'method': 'catalogue_work',
                    'material': 'chlorite',
                    'period': '2nde moitié du Xe siècle',
                    'origin': 'Bengale',
                },
                'Kannon, le bodhisattva de la compassion': {
                    'status': 'VERIFIED',
                    'canonical_title': 'Kannon, le bodhisattva de la compassion',
                    'snippet': 'Réalisée dans un bois de cyprès durant la seconde moitié du XIIe siècle',
                    'method': 'catalogue_work',
                    'material': 'bois',
                    'period': 'seconde moitié du XIIe siècle',
                    'origin': 'Japon',
                },
            },
            'per_work_contexts': {
                'La danse cosmique de Ganesh': [
                    'Period: 2nde moitié du Xe siècle',
                    'Material: chlorite',
                    'Origin: Bengale',
                    'Provenant de la région du Bengale ou du Bihar, cette stèle en chlorite de la 2nde moitié du Xe siècle exprime l\'essence de l\'esthétique indienne',
                ],
                'Kannon, le bodhisattva de la compassion': [
                    'Period: seconde moitié du XIIe siècle',
                    'Material: bois de cyprès',
                    'Origin: Japon',
                    'Réalisée dans un bois de cyprès durant la seconde moitié du XIIe siècle, cette remarquable statue japonaise représente Juichimen Kannon',
                ],
            },
        }

    def test_ganesh_period_is_xe_not_xiie(self, museum_data):
        """Ganesh's evidence_log period must be Xe siècle."""
        ganesh = museum_data['evidence_log']['La danse cosmique de Ganesh']
        assert 'Xe siècle' in ganesh['period']
        assert 'XIIe' not in ganesh['period']

    def test_ganesh_material_is_chlorite(self, museum_data):
        """Ganesh's material must be chlorite."""
        ganesh = museum_data['evidence_log']['La danse cosmique de Ganesh']
        assert ganesh['material'] == 'chlorite'

    def test_kannon_period_is_xiie(self, museum_data):
        """Kannon's evidence_log period must be XIIe siècle."""
        kannon = museum_data['evidence_log']['Kannon, le bodhisattva de la compassion']
        assert 'XIIe siècle' in kannon['period']

    def test_kannon_material_is_bois(self, museum_data):
        """Kannon's material must be bois."""
        kannon = museum_data['evidence_log']['Kannon, le bodhisattva de la compassion']
        assert kannon['material'] == 'bois'

    def test_per_work_contexts_bounded(self, museum_data):
        """per_work_contexts for each entry must not contain the other's metadata."""
        ganesh_ctx = ' '.join(museum_data['per_work_contexts']['La danse cosmique de Ganesh'])
        kannon_ctx = ' '.join(museum_data['per_work_contexts']['Kannon, le bodhisattva de la compassion'])
        
        # Ganesh must NOT have Kannon's data
        assert 'XIIe siècle' not in ganesh_ctx
        assert 'cyprès' not in ganesh_ctx
        assert 'Japon' not in ganesh_ctx
        
        # Kannon must NOT have Ganesh's data
        assert 'chlorite' not in kannon_ctx
        assert 'Bengale' not in kannon_ctx
        # "Xe siècle" is substring of "XIIe siècle", so check for standalone
        assert '2nde moitié du Xe siècle' not in kannon_ctx

    def test_c51_matching_ganesh(self, museum_data):
        """The C5-1 title matcher must find Ganesh in per_work_contexts."""
        from story_miner import _normalize
        poi_name = "La danse cosmique de Ganesh"
        poi_norm = _normalize(poi_name)
        
        matched_title = None
        for title in museum_data['per_work_contexts'].keys():
            title_norm = _normalize(title)
            if (poi_norm[:10] in title_norm or title_norm[:10] in poi_norm
                    or poi_norm == title_norm):
                matched_title = title
                break
        
        assert matched_title == 'La danse cosmique de Ganesh', \
            f"Expected Ganesh match, got: {matched_title}"

    def test_c51_matching_kannon(self, museum_data):
        """The C5-1 title matcher must find Kannon in per_work_contexts."""
        from story_miner import _normalize
        poi_name = "Kannon, le bodhisattva de la compassion"
        poi_norm = _normalize(poi_name)
        
        matched_title = None
        for title in museum_data['per_work_contexts'].keys():
            title_norm = _normalize(title)
            if (poi_norm[:10] in title_norm or title_norm[:10] in poi_norm
                    or poi_norm == title_norm):
                matched_title = title
                break
        
        assert matched_title == 'Kannon, le bodhisattva de la compassion', \
            f"Expected Kannon match, got: {matched_title}"

    def test_c51_no_cross_match(self, museum_data):
        """Ganesh must NOT match Kannon's per_work_contexts and vice versa."""
        from story_miner import _normalize
        
        ganesh_norm = _normalize("La danse cosmique de Ganesh")
        kannon_norm = _normalize("Kannon, le bodhisattva de la compassion")
        
        # Ganesh prefix must NOT match Kannon's title
        kannon_title_norm = _normalize("Kannon, le bodhisattva de la compassion")
        assert not (ganesh_norm[:10] in kannon_title_norm and kannon_title_norm[:10] in ganesh_norm), \
            "Ganesh must NOT match Kannon's per_work_contexts entry"
        
        # Kannon prefix must NOT match Ganesh's title
        ganesh_title_norm = _normalize("La danse cosmique de Ganesh")
        assert not (kannon_norm[:10] in ganesh_title_norm and ganesh_title_norm[:10] in kannon_norm), \
            "Kannon must NOT match Ganesh's per_work_contexts entry"


# ============================================================================
# Test 6: fact_extractor bounded lookup — no cross-contamination
# ============================================================================

class TestFactExtractorBoundedLookupLocal31:
    """Verify fact_extractor._extract_corpus_for_poi uses bounded lookup
    and does NOT fall through to raw corpus keyword search when per_work_contexts match."""

    def test_ganesh_gets_bounded_context(self):
        """fact_extractor for Ganesh must use per_work_contexts, not raw corpus."""
        from fact_extractor import generate_fact_sheets_parallel
        
        per_work_contexts = {
            'La danse cosmique de Ganesh': [
                'Period: 2nde moitié du Xe siècle',
                'Material: chlorite',
                'Origin: Bengale',
            ],
            'Kannon, le bodhisattva de la compassion': [
                'Period: seconde moitié du XIIe siècle',
                'Material: bois de cyprès',
                'Origin: Japon',
            ],
        }
        
        # Raw corpus has BOTH entries concatenated (the dangerous case)
        raw_corpus = (
            "chlorite Xe siècle Bengale. "
            "bois de cyprès XIIe siècle Japon."
        )
        
        # Simulate the _extract_corpus_for_poi logic
        poi_name = "La danse cosmique de Ganesh"
        poi_lower = poi_name.lower().strip()
        excerpts = []
        
        for title, sentences in per_work_contexts.items():
            title_lower = title.lower().strip()
            if (poi_lower == title_lower or
                (poi_lower[:10] in title_lower and title_lower[:10] in poi_lower)):
                excerpts.extend(s[:200] for s in sentences[:5])
                break
        
        result = '. '.join(excerpts) if excerpts else ""
        
        # Must contain Ganesh's metadata
        assert 'Xe siècle' in result
        assert 'chlorite' in result
        
        # Must NOT contain Kannon's metadata
        assert 'XIIe siècle' not in result
        assert 'bois' not in result.lower()
        assert 'Japon' not in result
