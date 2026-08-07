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


# ─── BOUNCE FIX TESTS: false positive elimination ────────────────────────────
# These target the three false-positive classes identified in the LEAD bounce:
# 1. "Treat Page" — closing offer boilerplate folded into last stop
# 2. Stop titles counted as people (Chez Palmyre, La Voglia, Le Safari, etc.)
# 3. Partial name deduplication (Kenzo vs Kenzo Tange)


class TestClosingOfferExcluded:
    """Closing offer boilerplate must not contribute facts to any stop."""

    def test_treat_page_not_a_person(self):
        """'Treat Page' from the closing offer must not appear as a person."""
        from tour_rubric_scorer import parse_tour
        tour_text = (
            "Stop 5: La Voglia\n\n"
            "La Voglia showcases a blend of Italian culinary passion. "
            "Chef Marco created a unique menu.\n\n"
            "That's 5 stops — Acchiardo, established in 1927 by Madalin "
            "Acchiardo in Niçoise tradition and Le Safari, where Franck "
            "Cerutti first introduced pizzas to Nice. If you would like to "
            "eat nearby we can build you a restaurant tour, and the Treat "
            "Page shows whether there are real savings at local shops and "
            "restaurants around here.\n"
        )
        stops = parse_tour(tour_text)
        assert len(stops) == 1
        # The closing offer must be stripped from the body
        assert "Treat Page" not in stops[0]['body'], (
            f"Closing offer was not stripped. Body: {stops[0]['body'][:200]}"
        )

    def test_closing_offer_people_not_counted(self):
        """People mentioned only in the closing offer must not appear in facts."""
        from tour_rubric_scorer import parse_tour
        tour_text = (
            "Stop 3: Final Stop\n\n"
            "The view from here is spectacular. You can see the bay.\n\n"
            "That's 3 stops and 2 kilometres — Nicole Rubi for Niçoise "
            "cuisine and Le Bistro du Port, a family-run establishment. "
            "If you would like to eat nearby we can build you a restaurant "
            "tour, and the Treat Page shows whether there are real savings.\n"
        )
        stops = parse_tour(tour_text)
        sa = analyze_stop(stops[0], stops)
        assert "Nicole Rubi" not in sa.named_people, (
            f"Closing-offer person leaked: {sa.named_people}"
        )
        assert "Treat Page" not in sa.named_people, (
            f"Treat Page leaked: {sa.named_people}"
        )


class TestStopTitlesNotPeople:
    """A tour's own stop titles and venue names must not be detected as people."""

    def test_la_voglia_is_stop_title(self):
        """'La Voglia' is a stop title in this tour — not a person."""
        text = (
            "La Voglia, a cozy Italian restaurant, serves fresh pasta daily. "
            "The warmth of the place invites lingering over espresso."
        )
        all_stops = [
            _make_stop("intro text", index=1, title="La Rossettisserie"),
            _make_stop("other text", index=2, title="Acchiardo"),
            _make_stop(text, index=3, title="La Voglia"),
        ]
        sa = analyze_stop(all_stops[2], all_stops)
        assert "La Voglia" not in sa.named_people, (
            f"Stop title 'La Voglia' detected as person: {sa.named_people}"
        )

    def test_le_safari_is_stop_title(self):
        """'Le Safari' referenced in another stop — it's a stop title, not a person."""
        text = (
            "As you leave Le Safari, the memories of fresh seafood linger. "
            "Le Safari, a Mediterranean gem, offered the finest catch."
        )
        all_stops = [
            _make_stop(text, index=5, title="La Voglia"),
            _make_stop("safari text", index=4, title="Le Safari"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Le Safari" not in sa.named_people, (
            f"Stop title 'Le Safari' detected as person: {sa.named_people}"
        )

    def test_chez_palmyre_is_stop_title(self):
        """'Chez Palmyre' as a stop title should not be a person."""
        text = (
            "Chez Palmyre, a traditional Niçoise eatery, welcomed guests "
            "for decades with its hearty regional fare."
        )
        all_stops = [
            _make_stop(text, index=1, title="Chez Palmyre"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Chez Palmyre" not in sa.named_people, (
            f"Stop title 'Chez Palmyre' detected as person: {sa.named_people}"
        )

    def test_arts_asiatiques_is_stop_title(self):
        """'Arts Asiatiques' as part of museum title must not be a person."""
        text = (
            "The Musee des Arts Asiatiques, a modern building, houses "
            "the collection of Asian art from across the continent."
        )
        all_stops = [
            _make_stop(text, index=1, title="Musée des Arts Asiatiques"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Arts Asiatiques" not in sa.named_people, (
            f"'Arts Asiatiques' (venue name) detected as person: {sa.named_people}"
        )

    def test_real_person_still_detected_alongside_title(self):
        """A real person in the same stop as a title reference must still be found."""
        text = (
            "Palmyre Moni, a Tuscan restaurateur, founded Chez Palmyre "
            "in 1926 bringing Italian flavors to this Niçoise street."
        )
        all_stops = [
            _make_stop(text, index=3, title="Chez Palmyre"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Palmyre Moni" in sa.named_people, (
            f"Real person missed: {sa.named_people}"
        )
        assert "Chez Palmyre" not in sa.named_people, (
            f"Stop title leaked: {sa.named_people}"
        )


class TestPartialNameDeduplication:
    """Partial names must be folded into their fuller form."""

    def test_kenzo_folded_into_kenzo_tange(self):
        """'Kenzo' alone should be folded into 'Kenzo Tange' when both appear."""
        text = (
            "Kenzo Tange, a renowned architect, designed this building. "
            "The vision of Kenzo shaped modern Japanese architecture."
        )
        all_stops = [
            _make_stop(text, index=3, title="Architecture Hall"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        # Kenzo Tange should be present (the full name)
        assert "Kenzo Tange" in sa.named_people, (
            f"'Kenzo Tange' not found: {sa.named_people}"
        )
        # 'Kenzo' alone should NOT appear separately
        kenzo_alone = [p for p in sa.named_people if p == "Kenzo"]
        assert not kenzo_alone, (
            f"Partial name 'Kenzo' not folded into 'Kenzo Tange': {sa.named_people}"
        )

    def test_chef_dominique_le_truncation(self):
        """'Chef Dominique Le' is a truncated extraction — should be deduplicated
        against 'Dominique Le Stanc' if both appear."""
        text = (
            "Dominique Le Stanc, a celebrated chef, transformed the menu. "
            "The artistry of Chef Dominique Le Stanc earned critical acclaim."
        )
        all_stops = [
            _make_stop(text, index=3, title="La Merenda"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        # Should not have both "Dominique Le" and "Dominique Le Stanc"
        people_lower = [p.lower() for p in sa.named_people]
        # Count distinct entries that contain "dominique"
        dominique_entries = [p for p in sa.named_people if "Dominique" in p]
        assert len(dominique_entries) <= 1, (
            f"Partial name not deduplicated: {dominique_entries}"
        )


class TestPreviousFixesStillWork:
    """Regression: the five cases from the original task must still pass."""

    def test_franck_cerutti_appositive(self):
        """The original diagnosed case: appositive detection."""
        text = (
            "Franck Cerutti, a culinary master with three Michelin stars, "
            "introduced the delectable pizzas to Nice's food scene."
        )
        sa = analyze_stop(_make_stop(text), [_make_stop(text)])
        assert "Franck Cerutti" in sa.named_people

    def test_nice_not_a_person(self):
        """'Nice, a coastal city' — the appositive guard blocks it."""
        text = (
            "Nice, a coastal city, offers visitors sun-drenched beaches "
            "and a vibrant cultural scene year-round."
        )
        sa = analyze_stop(_make_stop(text, title="Nice"), [_make_stop(text, title="Nice")])
        assert "Nice" not in sa.named_people

    def test_cours_saleya_not_a_person(self):
        """'Cours Saleya, a historic square' — blocked by place noun guard."""
        text = (
            "Cours Saleya, a historic square, hosts the daily flower market "
            "where locals and visitors mingle among colorful stalls."
        )
        sa = analyze_stop(_make_stop(text, title="Market"), [_make_stop(text, title="Market")])
        # "Cours Saleya" contains "square" (via _NOT_A_PERSON_RE) — blocked
        # Actually _NOT_A_PERSON_RE checks the name itself; "Cours Saleya" has
        # neither "square" nor other blockers. But the appositive place guard
        # catches "historic square" in the clause.
        people_names = [p.lower() for p in sa.named_people]
        assert "cours saleya" not in people_names

    def test_toyohara_chikanobu_detected(self):
        """Museum person with appositive still detected."""
        text = (
            "Toyohara Chikanobu, an ukiyo-e printmaker, depicted the "
            "Meiji court in vibrant woodblock prints."
        )
        sa = analyze_stop(_make_stop(text, title="Prints"), [_make_stop(text, title="Prints")])
        assert "Toyohara Chikanobu" in sa.named_people

    def test_clinking_glasses_still_zero(self):
        """Atmospheric filler: zero facts."""
        text = (
            "A mix of laughter and clinking glasses creating a symphony of "
            "conviviality fills the evening air as diners gather beneath "
            "the warm glow of overhead lights."
        )
        sa = analyze_stop(_make_stop(text, title="Ambiance"), [_make_stop(text, title="Ambiance")])
        assert sa.distinct_fact_count == 0


# ─── BOUNCE R2 TESTS: corrected title rule ─────────────────────────────────
# The title exclusion was too blunt — it extracted sub-phrases from within
# longer titles and excluded real people (Ulysses Grant, Andô Naoyuki).
# Corrected: only exclude names that ARE the full stop title.


class TestTitleRuleCorrected:
    """Person names within longer titles must be KEPT."""

    def test_ulysses_grant_within_longer_title(self):
        """'Ulysses Grant' within 'Ulysses Grant au Japon' is a person, not a venue."""
        text = (
            "The print depicts the momentous reception of Ulysses Grant, "
            "the President of the United States, and his wife at the "
            "Imperial Palace in Japan. The woodblock print Ulysses Grant "
            "au Japon stands as a testament to the power of art."
        )
        all_stops = [
            _make_stop(text, index=5, title="Ulysses Grant au Japon"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Ulysses Grant" in sa.named_people, (
            f"Person within longer title should be kept: {sa.named_people}"
        )

    def test_ando_naoyuki_within_longer_title(self):
        """'Andô Naoyuki' within 'L'Armure d'Andô Naoyuki' is a person."""
        text = (
            "Andô Naoyuki, a legendary samurai, commissioned this armour "
            "in the Edo period for ceremonial use."
        )
        all_stops = [
            _make_stop(text, index=1, title="L'Armure d'Andô Naoyuki"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Andô Naoyuki" in sa.named_people, (
            f"Person within longer title should be kept: {sa.named_people}"
        )

    def test_full_title_still_excluded(self):
        """A name that IS the full title is still excluded (venue)."""
        text = (
            "Chez Palmyre, a traditional Niçoise eatery, welcomed guests "
            "for decades with its hearty regional fare."
        )
        all_stops = [
            _make_stop(text, index=1, title="Chez Palmyre"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Chez Palmyre" not in sa.named_people, (
            f"Full title should be excluded: {sa.named_people}"
        )

    def test_la_merenda_full_title_excluded(self):
        """'La Merenda' as the full title is excluded."""
        text = (
            "La Merenda, a tiny Niçoise bistro, serves no-frills regional "
            "dishes prepared with local ingredients."
        )
        all_stops = [
            _make_stop(text, index=3, title="La Merenda"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "La Merenda" not in sa.named_people, (
            f"Full title should be excluded: {sa.named_people}"
        )


class TestPlaceAppositivePreventsVerbDetection:
    """When appositive identifies a place, the verb check must not override."""

    def test_arts_asiatiques_building_houses(self):
        """'Arts Asiatiques, a modern building, houses…' — 'houses' is not
        an action by a person; the appositive identifies the subject as a building."""
        text = (
            "The Musee des Arts Asiatiques, a modern building, houses "
            "the collection of Asian art from across the continent."
        )
        all_stops = [
            _make_stop(text, index=1, title="Musée des Arts Asiatiques"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Arts Asiatiques" not in sa.named_people, (
            f"Place with appositive should not be person: {sa.named_people}"
        )

    def test_old_port_harbor_hosts(self):
        """'Old Port, a historic harbor, hosts…' — 'hosts' after place appositive."""
        text = (
            "The Old Port, a historic harbor, hosts fishing boats and "
            "luxury yachts side by side in the Mediterranean sun."
        )
        all_stops = [
            _make_stop(text, index=2, title="Port Area"),
        ]
        sa = analyze_stop(all_stops[0], all_stops)
        assert "Old Port" not in sa.named_people, (
            f"Place with harbor appositive: {sa.named_people}"
        )


class TestTreatPageZeroAcrossAllTours:
    """'Treat Page' must appear in zero stops across all scorable tours."""

    def test_treat_page_stripped_from_restaurant_tour(self):
        """The closing offer in LOCAL318 restaurant tour is stripped."""
        from tour_rubric_scorer import parse_tour
        import os
        tour_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL318_5stop_old_nice_restaurant.txt'
        )
        if not os.path.exists(tour_path):
            import pytest
            pytest.skip("Tour file not available")
        with open(tour_path) as f:
            text = f.read()
        stops = parse_tour(text)
        for stop in stops:
            assert "Treat Page" not in stop['body'], (
                f"Stop {stop['index']} still contains 'Treat Page' in body"
            )
            sa = analyze_stop(stop, stops)
            assert "Treat Page" not in sa.named_people, (
                f"Stop {stop['index']} has 'Treat Page' as person: {sa.named_people}"
            )
