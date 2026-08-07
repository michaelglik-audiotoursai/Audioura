"""LOCAL-333: structural fact detection for non-museum domains.

Two diagnosed failures fixed by a GENERAL structural model (not vocabulary):
1. Person context: `Franck Cerutti` extracted by _PROPER_PHRASE_RE, not blocked
   by _NOT_A_PERSON_RE, but fails because _PERSON_CONTEXT_RE has no culinary
   vocabulary. Fix: detect the SHAPE (appositive after name, or past-tense verb
   following name) — not the specific word.
2. Spelled-out numerals: `three Michelin stars` fails because Track 2 wants
   numeral-then-noun adjacency and `Michelin` intervenes. Fix: allow up to 2
   intervening modifier words.

Guard rail: atmospheric filler MUST NOT register as fact.

Usage:
    python3 -m pytest tests/test_local333_fact_detector_nonmuseum.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tour_rubric_scorer import analyze_stop


def _make_stop(text: str, index: int = 4, title: str = "Le Safari") -> dict:
    return {'index': index, 'title': title, 'body': text}


class TestPersonContextStructural:
    """Structural model: appositive or past-tense verb identifies a person."""

    def test_appositive_introduced(self):
        """'Franck Cerutti, a culinary master ... introduced' — appositive shape."""
        text = (
            "Franck Cerutti, a culinary master with three Michelin stars, "
            "introduced the delectable pizzas to Nice's food scene."
        )
        sa = analyze_stop(_make_stop(text), [_make_stop(text)])
        assert "Franck Cerutti" in sa.named_people, (
            f"Expected 'Franck Cerutti' in named_people, got {sa.named_people}"
        )

    def test_appositive_tuscan_restaurateur(self):
        """'Palmyre Moni, a Tuscan restaurateur, founded ...' — appositive shape."""
        text = (
            "Palmyre Moni, a Tuscan restaurateur, founded the establishment "
            "in 1926 and brought Italian flavors to this Niçoise street."
        )
        sa = analyze_stop(_make_stop(text, title="Chez Palmyre"), [_make_stop(text)])
        assert "Palmyre Moni" in sa.named_people, (
            f"Expected 'Palmyre Moni' in named_people, got {sa.named_people}"
        )

    def test_past_tense_verb_crafts(self):
        """'Chef David Marques crafts...' — the 'Chef' title-before-name pattern."""
        text = (
            "Chef David Marques crafts his daily special menu, continuing "
            "the tradition of blending regional techniques with personal passion."
        )
        sa = analyze_stop(_make_stop(text, title="La Voglia"), [_make_stop(text)])
        # The title pattern "Chef X" or the role-adjacent Track 3 should catch this
        found = any("David Marques" in p for p in sa.named_people)
        assert found, (
            f"Expected 'David Marques' in named_people, got {sa.named_people}"
        )

    def test_appositive_french_chef(self):
        """'Franck Cerutti, a French chef from Nice ...' — appositive."""
        text = (
            "Franck Cerutti, a French chef from Nice, first introduced these "
            "pizzas to the discerning palates of Nice here at Le Safari."
        )
        sa = analyze_stop(_make_stop(text), [_make_stop(text)])
        assert "Franck Cerutti" in sa.named_people, (
            f"Expected 'Franck Cerutti' in named_people, got {sa.named_people}"
        )

    def test_past_verb_opened(self):
        """Past-tense verb after a name identifies a person."""
        text = (
            "Marcel Dupont opened the first bakery on this corner in 1932, "
            "serving fresh croissants every morning."
        )
        sa = analyze_stop(_make_stop(text, title="Bakery"), [_make_stop(text)])
        assert "Marcel Dupont" in sa.named_people, (
            f"Expected 'Marcel Dupont' in named_people, got {sa.named_people}"
        )


class TestSpelledOutNumeralWithModifier:
    """Spelled-out numeral Track 2 must tolerate intervening modifiers."""

    def test_three_michelin_stars(self):
        """'three Michelin stars' should register as a measurement/number."""
        text = (
            "Franck Cerutti earned three Michelin stars for his innovative "
            "cuisine that blended traditional and modern techniques."
        )
        sa = analyze_stop(_make_stop(text), [_make_stop(text)])
        matches = [m for m in sa.measurements_numbers if 'star' in m]
        assert matches, (
            f"Expected 'three Michelin stars' or similar in measurements_numbers, "
            f"got {sa.measurements_numbers}"
        )

    def test_five_olympic_gold_medals(self):
        """Pattern should catch other proper-adjective modifiers."""
        text = (
            "The athlete won five Olympic gold medals during her career, "
            "setting records that stood for decades."
        )
        sa = analyze_stop(_make_stop(text, title="Sports Hall"), [_make_stop(text)])
        matches = [m for m in sa.measurements_numbers if 'medal' in m]
        assert matches, (
            f"Expected medal-related match in measurements_numbers, "
            f"got {sa.measurements_numbers}"
        )

    def test_two_heritage_sites(self):
        """Intervening words between numeral and noun (1 modifier)."""
        text = (
            "The city contains two Heritage sites that attract "
            "millions of visitors annually."
        )
        sa = analyze_stop(_make_stop(text, title="City Tour"), [_make_stop(text)])
        matches = [m for m in sa.measurements_numbers if 'site' in m]
        assert matches, (
            f"Expected site-related match in measurements_numbers, "
            f"got {sa.measurements_numbers}"
        )


class TestFillerNotCounted:
    """Atmospheric filler must NOT register as a fact."""

    def test_clinking_glasses_not_a_fact(self):
        """'a mix of laughter and clinking glasses creating a symphony of
        conviviality' is not a fact."""
        text = (
            "A mix of laughter and clinking glasses creating a symphony of "
            "conviviality fills the evening air as diners gather beneath "
            "the warm glow of overhead lights."
        )
        sa = analyze_stop(_make_stop(text, title="Ambiance"), [_make_stop(text)])
        assert sa.distinct_fact_count == 0, (
            f"Atmospheric filler should yield 0 facts, got {sa.distinct_fact_count}. "
            f"People={sa.named_people}, Numbers={sa.measurements_numbers}, "
            f"Dates={sa.dates_years}, Materials={sa.materials_techniques}"
        )

    def test_symphony_metaphor_not_a_fact(self):
        """Metaphorical language about atmosphere is not factual."""
        text = (
            "The narrow streets create a symphony of sounds where each "
            "footstep echoes against ancient walls, blending with the murmur "
            "of fountains and the distant call of seagulls overhead."
        )
        sa = analyze_stop(_make_stop(text, title="Streets"), [_make_stop(text)])
        assert sa.distinct_fact_count == 0, (
            f"Metaphorical atmosphere should yield 0 facts, got {sa.distinct_fact_count}"
        )


class TestNotAPersonGuard:
    """Geographic/institutional proper phrases must NOT be detected as people."""

    def test_old_nice_not_a_person(self):
        """'Old Nice' should be blocked — it's a place."""
        text = (
            "Old Nice, a charming district of the city, offers visitors "
            "winding streets and colorful facades dating from the 17th century."
        )
        sa = analyze_stop(_make_stop(text, title="Old Nice"), [_make_stop(text)])
        assert "Old Nice" not in sa.named_people, (
            f"'Old Nice' should not be in named_people: {sa.named_people}"
        )

    def test_le_safari_venue(self):
        """'Le Safari' has 'Le' as a particle — may be extracted. If extracted,
        it should not be blocked by _NOT_A_PERSON_RE (it's a restaurant name,
        not a person, but also not a place-category). The structural model may
        or may not fire depending on surrounding context. This test verifies
        the guard rail doesn't crash, not that Le Safari IS a person."""
        text = (
            "Le Safari serves traditional Niçoise cuisine in the heart of "
            "the old quarter, attracting both locals and tourists."
        )
        sa = analyze_stop(_make_stop(text, title="Le Safari"), [_make_stop(text)])
        # Just verify no crash and no assertion error
        assert isinstance(sa.named_people, list)


class TestStopOneFactCountNonZero:
    """Stop 1 of restaurant tour must score > 0 distinct facts."""

    def test_stop1_with_dates_and_people(self):
        """The stop mentions people + dates = verifiable facts."""
        text = (
            "From the old-school takes at Chez Acchiardo, established by "
            "Madalin Acchiardo in 1927, to the Tuscan influences at Chez "
            "Palmyre, founded by Palmyre Moni in 1926, these restaurants "
            "narrate tales of family legacies and immigrant influences. "
            "At La Voglia, Chef David Marques crafts his daily special menu, "
            "continuing the tradition of blending regional techniques with "
            "personal passion. In the stops ahead, you will discover the 1927 "
            "establishment of Acchiardo by Madalin Acchiardo and the "
            "introduction of pizzas by Franck Cerutti at Le Safari."
        )
        sa = analyze_stop(
            _make_stop(text, index=1, title="La Rossettisserie"),
            [_make_stop(text, index=1, title="La Rossettisserie")]
        )
        assert sa.distinct_fact_count > 0, (
            f"Stop 1 should have facts (dates: 1927, 1926; people expected), got 0. "
            f"People={sa.named_people}, Dates={sa.dates_years}, "
            f"Numbers={sa.measurements_numbers}"
        )
