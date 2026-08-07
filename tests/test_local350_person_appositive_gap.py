"""LOCAL-350: Appositive gap — relative clause and familial role noun detection.

Diagnosed failures:
1. Multi-word name + relative clause: "Madalin Acchiardo, who opened…" — the
   subject-pronoun guard in Check 2 (active verb) treated "who" as a subject
   change. But in a non-restrictive relative clause (, who <verb>), the
   antecedent IS the person performing the action. Fix: Check 1b fires on
   ", who <verb>" before the active-verb check's subject-change guard can block.

2. Single-word name + familial role noun: "her late husband Giuseppe" — no
   multi-word regex matches a single word, and "husband" was not in any
   existing detection track. Fix: Track 4 matches familial/identity role nouns
   immediately preceding a capitalised name.

Per D242: tests import production code and must fail against the unfixed version.

Usage:
    python3 -m pytest tests/test_local350_person_appositive_gap.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tour_rubric_scorer import analyze_stop


def _make_stop(text: str, index: int = 4, title: str = "Acchiardo") -> dict:
    return {'index': index, 'title': title, 'body': text}


class TestRelativeClauseDetection:
    """Check 1b: non-restrictive relative clause identifies a person."""

    def test_madalin_acchiardo_who_opened(self):
        """The exact sentence from LOCAL-349 restaurant stop 4."""
        text = (
            "Once a humble dream of a widow named Madalin Acchiardo, who opened "
            "the restaurant in 1927 with her late husband Giuseppe, the "
            "establishment has blossomed into a beloved culinary institution."
        )
        sa = analyze_stop(_make_stop(text), [_make_stop(text)])
        assert "Madalin Acchiardo" in sa.named_people, (
            f"Expected 'Madalin Acchiardo' via relative clause, got {sa.named_people}"
        )

    def test_relative_clause_with_unrelated_title(self):
        """Same sentence with an unrelated title — title exclusion is not the cause."""
        text = (
            "Once a humble dream of a widow named Madalin Acchiardo, who opened "
            "the restaurant in 1927 with her late husband Giuseppe, the "
            "establishment has blossomed into a beloved culinary institution."
        )
        sa = analyze_stop(_make_stop(text, title="The Old Bistro"), [_make_stop(text, title="The Old Bistro")])
        assert "Madalin Acchiardo" in sa.named_people, (
            f"Expected 'Madalin Acchiardo' regardless of title, got {sa.named_people}"
        )

    def test_generic_relative_clause_founded(self):
        """Generic: 'Jean Dupont, who founded the bakery in 1952'."""
        text = (
            "Jean Dupont, who founded the bakery in 1952, served the "
            "neighborhood for over forty years."
        )
        sa = analyze_stop(_make_stop(text, title="Bakery"), [_make_stop(text, title="Bakery")])
        assert "Jean Dupont" in sa.named_people, (
            f"Expected 'Jean Dupont' via relative clause, got {sa.named_people}"
        )

    def test_relative_clause_transformed(self):
        """'Maria Rossi, who transformed the tiny space into a beloved gathering place'."""
        text = (
            "Maria Rossi, who transformed the tiny space into a beloved "
            "gathering place, earned three culinary awards."
        )
        sa = analyze_stop(_make_stop(text, title="Café"), [_make_stop(text, title="Café")])
        assert "Maria Rossi" in sa.named_people, (
            f"Expected 'Maria Rossi' via relative clause, got {sa.named_people}"
        )

    def test_stative_who_is_not_person(self):
        """'Nice, who is located on the coast' — stative verb does NOT identify a person."""
        text = (
            "Nice, who is located on the stunning Mediterranean coast, "
            "draws millions of visitors each year."
        )
        sa = analyze_stop(_make_stop(text, title="Overview"), [_make_stop(text, title="Overview")])
        assert "Nice" not in sa.named_people, (
            f"'Nice, who is...' should not yield a person: {sa.named_people}"
        )

    def test_stative_who_was_not_person(self):
        """'The Basilica, who was designed...' — stative 'was' does NOT fire."""
        text = (
            "The Basilica, who was designed by a renowned architect, "
            "stands tall over the old town."
        )
        sa = analyze_stop(_make_stop(text, title="Basilica"), [_make_stop(text, title="Basilica")])
        # "The Basilica" is a 2-word article phrase — also blocked by article guard
        assert "The Basilica" not in sa.named_people


class TestFamilialRoleNounDetection:
    """Track 4: familial/identity role nouns preceding single-word names."""

    def test_husband_giuseppe(self):
        """'her late husband Giuseppe' — familial role noun identifies a person."""
        text = (
            "Once a humble dream of a widow named Madalin Acchiardo, who opened "
            "the restaurant in 1927 with her late husband Giuseppe, the "
            "establishment has blossomed into a beloved culinary institution."
        )
        sa = analyze_stop(_make_stop(text), [_make_stop(text)])
        assert "Giuseppe" in sa.named_people, (
            f"Expected 'Giuseppe' via familial role noun, got {sa.named_people}"
        )

    def test_wife_marguerite(self):
        """'his wife Marguerite' — familial role noun."""
        text = (
            "He returned to Nice with his wife Marguerite and opened a small "
            "bistro on the corner of Rue Droite."
        )
        sa = analyze_stop(_make_stop(text, title="Bistro"), [_make_stop(text, title="Bistro")])
        assert "Marguerite" in sa.named_people, (
            f"Expected 'Marguerite' via wife pattern, got {sa.named_people}"
        )

    def test_son_antoine(self):
        """'their son Antoine' — familial role noun."""
        text = (
            "Their son Antoine took over the family business in 1965 and "
            "expanded the menu to include Provençal specialties."
        )
        sa = analyze_stop(_make_stop(text, title="Restaurant"), [_make_stop(text, title="Restaurant")])
        assert "Antoine" in sa.named_people, (
            f"Expected 'Antoine' via son pattern, got {sa.named_people}"
        )

    def test_named_keyword_with_person_context(self):
        """'a widow named Giuseppe' — 'named' not preceded by copula."""
        text = "She was a widow named Giuseppe who ran a small shop on the corner."
        sa = analyze_stop(_make_stop(text, title="Shop"), [_make_stop(text, title="Shop")])
        assert "Giuseppe" in sa.named_people, (
            f"Expected 'Giuseppe' via 'named' keyword, got {sa.named_people}"
        )

    def test_was_named_is_stative_not_person(self):
        """'was named Nice' — stative/passive naming of a place, NOT a person."""
        text = "The city was named Nice after the Greek word for victory."
        sa = analyze_stop(_make_stop(text, title="History"), [_make_stop(text, title="History")])
        assert "Nice" not in sa.named_people, (
            f"'was named Nice' should not yield a person: {sa.named_people}"
        )

    def test_husband_without_name_no_detection(self):
        """'her husband joined' with no capitalised name — nothing to detect."""
        text = "Her husband joined the celebration and the evening was filled with joy."
        sa = analyze_stop(_make_stop(text, title="Celebration"), [_make_stop(text, title="Celebration")])
        assert sa.named_people == [], (
            f"No capitalised name after 'husband': {sa.named_people}"
        )


class TestGuardsIntact:
    """Verify existing guards are not regressed by LOCAL-350 changes."""

    def test_filler_clinking_glasses(self):
        """Atmospheric filler must yield zero facts."""
        text = (
            "A mix of laughter and clinking glasses creating a symphony of "
            "conviviality fills the evening air as diners gather beneath "
            "the warm glow of overhead lights."
        )
        sa = analyze_stop(_make_stop(text, title="Ambiance"), [_make_stop(text, title="Ambiance")])
        assert sa.distinct_fact_count == 0, (
            f"Filler must yield 0 facts, got {sa.distinct_fact_count}. "
            f"People={sa.named_people}"
        )

    def test_nice_coastal_city_not_person(self):
        """'Nice, a coastal city, offers…' — place appositive, not a person."""
        text = "Nice, a coastal city, offers stunning views of the Mediterranean."
        sa = analyze_stop(
            _make_stop(text, title="Promenade des Anglais"),
            [_make_stop(text, title="Promenade des Anglais")]
        )
        assert "Nice" not in sa.named_people, (
            f"'Nice, a coastal city' should not be a person: {sa.named_people}"
        )

    def test_d247_ulysses_grant_inside_longer_title(self):
        """D247: 'Ulysses Grant' within a longer title stays detected."""
        text = (
            "In 1879, the American general turned statesman, Ulysses Grant, embarked upon "
            "his historic visit to Japan. The xylogravure was crafted by Toyohara Chikanobu."
        )
        sa = analyze_stop(
            _make_stop(text, title="Ulysses Grant au Japon"),
            [_make_stop(text, title="Ulysses Grant au Japon")]
        )
        assert "Ulysses Grant" in sa.named_people, (
            f"D247: 'Ulysses Grant' must be kept: {sa.named_people}"
        )

    def test_d247_ando_naoyuki_inside_longer_title(self):
        """D247: 'Andô Naoyuki' within a longer title stays detected."""
        text = (
            "Historically, Andô Naoyuki, heir to the Tanabe domain and destined for "
            "the title of baron, wore this armor at a pivotal moment in his life."
        )
        sa = analyze_stop(
            _make_stop(text, title="L'Armure d'Andô Naoyuki"),
            [_make_stop(text, title="L'Armure d'Andô Naoyuki")]
        )
        found = "Andô Naoyuki" in sa.named_people or "Ando Naoyuki" in sa.named_people
        assert found, (
            f"D247: 'Andô Naoyuki' must be kept: {sa.named_people}"
        )

    def test_chez_palmyre_excluded_as_whole_title(self):
        """'Chez Palmyre' IS the whole title → excluded."""
        text = "Chez Palmyre, a Niçoise institution, has served traditional cuisine since 1926."
        sa = analyze_stop(
            _make_stop(text, title="Chez Palmyre"),
            [_make_stop(text, title="Chez Palmyre")]
        )
        assert "Chez Palmyre" not in sa.named_people

    def test_la_merenda_excluded_as_whole_title(self):
        """'La Merenda' IS the whole title → excluded."""
        text = "La Merenda, a tiny restaurant with just 26 seats, offers no reservations."
        sa = analyze_stop(
            _make_stop(text, title="La Merenda"),
            [_make_stop(text, title="La Merenda")]
        )
        assert "La Merenda" not in sa.named_people


class TestFactCountBandChange:
    """The Acchiardo stop must move from 1 fact (date only) to 3 facts."""

    def test_acchiardo_stop_fact_count(self):
        """Stop 4 of the restaurant tour: 2 people + 1 date = 3 distinct facts."""
        text = (
            "Once a humble dream of a widow named Madalin Acchiardo, who opened "
            "the restaurant in 1927 with her late husband Giuseppe, the "
            "establishment has blossomed into a beloved culinary institution."
        )
        sa = analyze_stop(_make_stop(text), [_make_stop(text)])
        assert sa.distinct_fact_count == 3, (
            f"Expected 3 facts (2 people + 1 date), got {sa.distinct_fact_count}. "
            f"People={sa.named_people}, Dates={sa.dates_years}"
        )
