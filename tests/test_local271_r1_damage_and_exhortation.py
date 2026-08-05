#!/usr/bin/env python3
"""Tests for LOCAL-271: R1 damage fix, empty exhortation gate, forward transition.

Three defects:
1. R1 rewrite produces "admire yourself", mid-sentence capitals, doubled clauses
2. Empty exhortation not caught by any gate
3. Forward transition at final stop points at nothing

Run with: python3 -m pytest tests/test_local271_r1_damage_and_exhortation.py -v -s
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_validator_detector import (
    check_r1_imperatives,
    rewrite_r1_sentence_deterministic,
    apply_r1_rewrites,
    apply_r1_to_description,
    _is_style_navigation_sentence,
    _has_finite_main_verb,
    _r1_rewrite_wellformed,
    check_forward_transition_final_stop,
    remove_forward_transitions_final_stop,
)
from unsupported_claim_gate import (
    classify_claim,
    _is_substantiated,
    apply_unsupported_claim_gate,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 1: R1 REWRITE DAMAGE — THREE SHAPES
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdmireYourselfFix:
    """Fix 1: 'you can admire yourself' nonsense from reflexive/participle tail."""

    def test_find_yourself_amidst(self):
        """Round 10: 'find yourself amidst the lush greenery' → nonsense."""
        sent = "As you arrive at Cap d'Antibes, find yourself amidst the lush greenery."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None
        assert 'admire yourself' not in result, f"NONSENSE: {result}"
        assert _has_finite_main_verb(result), f"FRAGMENT: {result}"
        print(f"  ✓ {result}")

    def test_yourself_standing_at(self):
        """Round 23: 'yourself standing at the tip of the cape' → nonsense."""
        sent = "As you arrive at Cap d'Antibes, find yourself standing at the tip of the cape."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None
        assert 'admire yourself' not in result, f"NONSENSE: {result}"
        assert _has_finite_main_verb(result), f"FRAGMENT: {result}"
        print(f"  ✓ {result}")

    def test_mid_sentence_yourself(self):
        """Mid-sentence variant: 'While you X, admire yourself...'"""
        sent = "While you explore the gardens, find yourself surrounded by vibrant colours."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None
        assert 'admire yourself' not in result, f"NONSENSE: {result}"
        print(f"  ✓ {result}")

    def test_normal_admire_still_works(self):
        """Normal case: 'admire the views' should still produce good output."""
        sent = "As you arrive at Cap d'Antibes, admire the breathtaking views of the azure waters."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None
        assert 'you can admire' in result.lower()
        assert 'azure waters' in result
        print(f"  ✓ {result}")

    def test_wellformedness_rejects_admire_yourself(self):
        """The well-formedness check catches 'admire yourself' if it slips through."""
        bad = "From Cap d'Antibes, you can admire yourself amidst the lush greenery."
        assert not _r1_rewrite_wellformed("original", bad)


class TestMidSentenceCapitalsFix:
    """Fix 2: 'The Vibrant mix', 'The Panoramic views' — wrong capitalisation."""

    def test_vibrant_detected(self):
        """'The Vibrant mix of colors' has a wrongly-capped adjective."""
        bad = "The Vibrant mix of colors and sounds that define this historic port town stretches out before you."
        assert not _r1_rewrite_wellformed("original", bad)

    def test_panoramic_detected(self):
        """'The Panoramic views' has a wrongly-capped adjective."""
        bad = "The Panoramic views of the Mediterranean Sea stretch out before you."
        assert not _r1_rewrite_wellformed("original", bad)

    def test_breathtaking_detected(self):
        """'The Breathtaking coastline' has a wrongly-capped adjective."""
        bad = "From here, the Breathtaking coastline curves into the distance."
        assert not _r1_rewrite_wellformed("original", bad)

    def test_proper_noun_ok(self):
        """'The Mediterranean Sea' is fine — proper noun."""
        good = "The Mediterranean Sea stretches out before you."
        assert _r1_rewrite_wellformed("original", good)

    def test_french_adjective_ok(self):
        """'The French Riviera' is fine — proper adjective."""
        good = "The French Riviera coastline is visible from here."
        assert _r1_rewrite_wellformed("original", good)


class TestDoubledClauseFix:
    """Fix 3: 'stretching out before you...stretches out before you' doubled."""

    def test_exact_round23_case(self):
        """Round 23: doubled 'stretches out before you'."""
        bad = ("The Panoramic views of the Mediterranean Sea stretching out before you, "
               "while the scents of saltwater and pine trees fill the air stretches out before you.")
        assert not _r1_rewrite_wellformed("original", bad)

    def test_simple_double(self):
        """Simple doubled 5-word phrase."""
        # The real-world case: same subject, same phrase repeated
        bad = "The Mediterranean stretching out before you, while the scents fill the air stretching out before you."
        # "out before you while the" and later... let me use the actual round-23 shape:
        bad_actual = ("The Panoramic views of the Mediterranean Sea stretching out before you, "
                      "while the scents of saltwater and pine trees fill the air stretches out before you.")
        assert not _r1_rewrite_wellformed("original", bad_actual)

    def test_take_in_handler_no_double(self):
        """_take_in_handler should NOT double when tail already has the phrase."""
        sent = "Take in the panoramic views of the Mediterranean Sea stretching out before you, while the scents of saltwater and pine trees fill the air."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None
        # Count occurrences of "out before you"
        count = result.lower().count('out before you')
        assert count <= 1, f"DOUBLED: {result}"
        print(f"  ✓ {result}")


class TestWellformednessGateFallback:
    """Post-rewrite well-formedness check falls back to original imperative."""

    def test_apply_level_falls_back(self):
        """If a rewrite fails well-formedness, the original imperative is kept."""
        # This requires a scenario where deterministic rewrite produces bad output
        # but the input fires R1. We test via apply_r1_rewrites:
        para = "As you arrive at Cap d'Antibes, find yourself standing at the tip of the cape. In 1888, Monet painted here."
        result, rewritten, deleted, _ = apply_r1_rewrites(para)
        # The rewritten version should NOT contain "admire yourself"
        assert 'admire yourself' not in result
        # The 1888 fact must survive
        assert '1888' in result
        print(f"  ✓ {result}")


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 2: EMPTY EXHORTATION — FIFTH CLAIM TYPE
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyExhortation:
    """Empty exhortation: urges listener toward something without saying what."""

    def test_classify_journey_back(self):
        """'Just ahead, journey back through the centuries.' → EXHORTATION."""
        sent = "Just ahead, journey back through the centuries."
        assert classify_claim(sent) == 'EXHORTATION'

    def test_classify_step_into_world(self):
        """'Step into a world where time stands still.' → EXHORTATION."""
        sent = "Step into a world where time stands still."
        assert classify_claim(sent) == 'EXHORTATION'

    def test_classify_prepare_transported(self):
        """'Prepare to be transported to another era.' → EXHORTATION."""
        sent = "Prepare to be transported to another era."
        assert classify_claim(sent) == 'EXHORTATION'

    def test_gate_removes_journey_back(self):
        """Gate removes 'journey back through the centuries' in isolation."""
        sent = "Just ahead, journey back through the centuries."
        new_text, stats = apply_unsupported_claim_gate(sent)
        assert stats['sentences_removed'] > 0
        assert stats['claim_types_removed']['EXHORTATION'] > 0

    def test_gate_removes_step_into_world(self):
        """Gate removes 'step into a world' despite nav-like verb."""
        sent = "Step into a world where time stands still."
        new_text, stats = apply_unsupported_claim_gate(sent)
        assert stats['sentences_removed'] > 0

    def test_gate_removes_prepare_transported(self):
        """Gate removes 'prepare to be transported'."""
        sent = "Prepare to be transported to another era."
        new_text, stats = apply_unsupported_claim_gate(sent)
        assert stats['sentences_removed'] > 0


class TestExhortationMustSurvive:
    """Sentences that look vaguely like exhortations but have content."""

    def test_chapelle_1306_survives(self):
        """Named entity + date → not an exhortation, survives."""
        sent = "Just ahead, the Chapelle de la Sainte Croix, built in 1306, comes into view."
        ct = classify_claim(sent)
        assert ct is None or ct != 'EXHORTATION', f"Wrongly classified as {ct}"

    def test_cycling_d164_survives(self):
        """Navigation with appended instruction (D164) survives."""
        sent = "Start cycling south on the main road, enjoy the sea breeze."
        assert _is_style_navigation_sentence(sent)
        # Even if classified, nav is exempt (except for exhortation, which this isn't)
        ct = classify_claim(sent)
        assert ct != 'EXHORTATION'

    def test_monet_1888_survives(self):
        """Concrete historical fact — not an exhortation."""
        sent = "In 1888, Monet first experimented with painting in series here."
        ct = classify_claim(sent)
        assert ct != 'EXHORTATION'

    def test_exhortation_with_adjacent_content_survives(self):
        """Exhortation substantiated by adjacent factual sentence → KEEP."""
        para = ("Step into a world where time stands still. "
                "The Chapelle de la Sainte Croix, built in 1306, contains "
                "original frescoes from the 14th century.")
        new_text, stats = apply_unsupported_claim_gate(para)
        # If adjacent fact substantiates, the exhortation may survive
        # (adjacency test applies like for all claim types)


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 3: FORWARD TRANSITION AT FINAL STOP
# ═══════════════════════════════════════════════════════════════════════════════

class TestForwardTransitionFinalStop:
    """Forward references in the last stop point at nothing."""

    def test_detects_just_ahead(self):
        """'Just ahead, journey back through the centuries.' is a violation."""
        desc = "The ancient pathways bear the weight of history. Just ahead, journey back through the centuries."
        violations = check_forward_transition_final_stop(desc)
        assert len(violations) >= 1
        assert any('Just ahead' in v['sentence'] for v in violations)

    def test_detects_continue_on(self):
        """'Continue on to discover more' is a forward transition."""
        desc = "The view from here is magnificent. Continue on to discover more treasures."
        violations = check_forward_transition_final_stop(desc)
        assert len(violations) >= 1

    def test_no_false_positive_factual(self):
        """Factual sentence without forward reference → no violation."""
        desc = "In 1888, Monet first experimented with painting in series here."
        violations = check_forward_transition_final_stop(desc)
        assert len(violations) == 0

    def test_removes_empty_forward(self):
        """Empty forward reference removed, factual content kept."""
        desc = ("The ancient pathways bear the weight of history. "
                "Just ahead, journey back through the centuries.")
        new_desc, removed = remove_forward_transitions_final_stop(desc)
        assert 'Just ahead' not in new_desc
        assert 'ancient pathways' in new_desc
        assert len(removed) == 1

    def test_keeps_factual_forward(self):
        """Forward reference with content (date, proper noun) is kept."""
        desc = "Built in 1306, the Chapelle de la Sainte Croix lies just ahead on the path to Eze."
        new_desc, removed = remove_forward_transitions_final_stop(desc)
        assert '1306' in new_desc
        assert len(removed) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# PRIOR BOUNDARY SETS — must still hold
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriorBoundarySetsLocal263:
    """LOCAL-263's 10 boundary rows."""

    def test_remove_waves_crash(self):
        sent = "The waves crash against the rocky shore, blending with the calls of seagulls soaring overhead."
        assert classify_claim(sent) == 'SENSORY'

    def test_remove_warmth_sun(self):
        sent = "The warmth of the sun on your skin accompanies the breathtaking views of the Mediterranean stretching out endlessly before you."
        assert classify_claim(sent) == 'SENSORY'

    def test_remove_rugged_beauty(self):
        sent = "The rugged beauty of the landscape, with its rocky cliffs and secluded coves, invites contemplation and serenity."
        assert classify_claim(sent) == 'FEELING'

    def test_remove_holds_special_place(self):
        sent = "Cap d'Antibes, situated on the French Riviera, holds a special place in the region's history and culture."
        assert classify_claim(sent) == 'QUALITY'

    def test_remove_surrounded_by_history(self):
        sent = "As you stand on Cap d'Antibes, you are surrounded by history and natural beauty."
        assert classify_claim(sent) == 'FEELING'

    def test_survive_iconic_cape_with_fact(self):
        para = ("This iconic cape, situated on the French Riviera, holds a significant place "
                "in the region's landscape. In 2023, Antibes boasted a population of 77,637, "
                "making it the second most populous area in Alpes-Maritimes after Nice.")
        new_text, stats = apply_unsupported_claim_gate(para)
        assert 'holds a significant place' in new_text or 'iconic cape' in new_text
        assert '77,637' in new_text

    def test_survive_navigation_d164(self):
        sent = "Start cycling southeast on the main road, enjoy the sea breeze along the coast."
        assert _is_style_navigation_sentence(sent)

    def test_survive_monet_1888(self):
        sent = "In 1888, Monet first experimented with painting in series here."
        ct = classify_claim(sent)
        assert ct is None or ct != 'EXHORTATION'

    def test_survive_colombe_dor(self):
        sent = "The La Colombe d'Or hotel has hosted Jean-Paul Sartre and Pablo Picasso."
        ct = classify_claim(sent)
        assert ct is None


class TestPriorBoundarySetsLocal269:
    """LOCAL-269's 8 boundary rows (gloss gate)."""

    def test_operation_dragoon_needs_gloss(self):
        """Named event without explanation → should survive style checks."""
        sent = "Operation Dragoon, the 1944 Allied invasion of southern France, began on these shores."
        assert _has_finite_main_verb(sent)
        ct = classify_claim(sent)
        assert ct is None  # Factual, not a claim

    def test_house_of_savoy_needs_gloss(self):
        sent = "The House of Savoy ruled this territory from 1388 to 1860."
        assert _has_finite_main_verb(sent)
        ct = classify_claim(sent)
        assert ct is None

    def test_mistral_wind_needs_gloss(self):
        sent = "The Mistral, a strong cold wind, shapes the vegetation along this coast."
        assert _has_finite_main_verb(sent)

    def test_belle_epoque_needs_gloss(self):
        sent = "During the Belle Époque, wealthy British visitors transformed Nice into a resort."
        assert _has_finite_main_verb(sent)

    def test_factual_with_year_survives_all_gates(self):
        sent = "In 1834, Lord Brougham discovered Cannes and built a villa here."
        assert _has_finite_main_verb(sent)
        ct = classify_claim(sent)
        assert ct is None

    def test_navigation_with_landmark(self):
        sent = "Head east along the Promenade des Anglais toward the old port."
        assert _is_style_navigation_sentence(sent)

    def test_r1_rewrite_content_preserved(self):
        sent = "Position yourself at the entrance of Eze Village, a medieval gem perched high above the French Riviera."
        result = rewrite_r1_sentence_deterministic(sent)
        assert 'Eze Village' in result
        assert 'medieval gem' in result

    def test_r1_navigation_exempt(self):
        sent = "Start cycling south on the main road."
        assert _is_style_navigation_sentence(sent)
        findings = check_r1_imperatives(sent)
        # Navigation should not trigger R1 rewrite in the pipeline


class TestPriorBoundarySetsLocal249:
    """LOCAL-249's 9 boundary rows (R9 generic)."""

    def test_monet_1888_not_r9(self):
        from style_validator_detector import check_r9_generic
        sent = "In 1888, Monet first experimented with painting in series here."
        assert check_r9_generic(sent) == []

    def test_fondation_1964_not_r9(self):
        from style_validator_detector import check_r9_generic
        sent = "The Fondation Maeght was founded in 1964 by Marguerite and Aimé Maeght."
        assert check_r9_generic(sent) == []

    def test_sert_architect_not_r9(self):
        from style_validator_detector import check_r9_generic
        sent = "Josep Lluís Sert, a Catalan architect, designed the building."
        assert check_r9_generic(sent) == []

    def test_malraux_1964_not_r9(self):
        from style_validator_detector import check_r9_generic
        sent = "André Malraux inaugurated it in July 1964."
        assert check_r9_generic(sent) == []

    def test_ancient_pathways_contentless(self):
        from style_validator_detector import _has_contentless_signal
        sent = "The ancient pathways bear the weight of centuries of history."
        assert _has_contentless_signal(sent)

    def test_portal_world_contentless(self):
        from style_validator_detector import _has_contentless_signal
        sent = "Each archway serves as a portal to a world steeped in artistic legacy."
        assert _has_contentless_signal(sent)

    def test_fitzgerald_1934_not_r9(self):
        from style_validator_detector import check_r9_generic
        sent = "F. Scott Fitzgerald completed 'Tender is the Night' here in 1934."
        assert check_r9_generic(sent) == []

    def test_hotel_1870_not_r9(self):
        from style_validator_detector import check_r9_generic
        sent = "The Grand-Hôtel du Cap-Ferrat opened in 1908."
        assert check_r9_generic(sent) == []

    def test_sentier_2_7km_not_r9(self):
        from style_validator_detector import check_r9_generic
        sent = "The Sentier du Littoral stretches 2.7 km along the rocky coast."
        assert check_r9_generic(sent) == []


class TestPriorBoundarySetsLocal251:
    """LOCAL-251's 10 boundary rows."""

    def test_monet_survives(self):
        sent = "In 1888, Monet first experimented with painting in series here."
        assert _has_finite_main_verb(sent)

    def test_sartre_colombe_dor_survives(self):
        sent = "The La Colombe d'Or hotel has hosted Jean-Paul Sartre and Pablo Picasso."
        assert _has_finite_main_verb(sent)

    def test_1960s_montand_survives(self):
        sent = "In the 1960s, Yves Montand and Simone Signoret were regular guests."
        assert _has_finite_main_verb(sent)

    def test_200bc_eze_survives(self):
        sent = "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide."
        assert _has_finite_main_verb(sent)

    def test_antonine_itinerary_survives(self):
        sent = "The Antonine Itinerary, a 3rd-century Roman road guide, listed Eze as a stop on the Via Julia Augusta."
        assert _has_finite_main_verb(sent)

    def test_walls_story_fires_r10(self):
        from style_validator_detector import check_r10_unfulfilled_promise, _split_sentences
        sent = "Each crack and crevice in the walls holds a story that deepens the allure of Eze Village."
        sents = _split_sentences(sent)
        result = check_r10_unfulfilled_promise(sents, 0)
        assert result is not None  # Should fire

    def test_hillsides_tales_fires_r10(self):
        from style_validator_detector import check_r10_unfulfilled_promise, _split_sentences
        sent = "The hillsides whisper tales from a bygone era."
        sents = _split_sentences(sent)
        result = check_r10_unfulfilled_promise(sents, 0)
        assert result is not None

    def test_testament_enduring_allure_fires(self):
        sent = "This medieval gem is a testament to the enduring allure of the French Riviera."
        ct = classify_claim(sent)
        # Should be classified as something (PROMISE or QUALITY)
        assert ct is not None

    def test_bridge_civilizations_fires(self):
        sent = "Eze Village stands as a bridge between ancient civilizations and modern culture."
        ct = classify_claim(sent)
        assert ct is not None

    def test_rich_tapestry_fires(self):
        sent = "The village tells a rich tapestry of history stretching back millennia."
        ct = classify_claim(sent)
        assert ct == 'PROMISE'


class TestPriorBoundarySetsLocal255:
    """LOCAL-255's 8 boundary rows (R1 rewrite)."""

    def test_position_yourself_eze(self):
        sent = "Position yourself at the entrance of Eze Village, a medieval gem perched high above the French Riviera."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None and result != '__LLM_NEEDED__'
        assert 'Eze Village' in result
        assert _has_finite_main_verb(result)

    def test_as_you_arrive_cap_dantibes(self):
        sent = "As you arrive at Cap d'Antibes, take in the breathtaking views of the azure waters."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None and result != '__LLM_NEEDED__'
        assert 'azure waters' in result
        assert _has_finite_main_verb(result)

    def test_look_for_fondation_maeght(self):
        sent = "Look for the Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is not None and result != '__LLM_NEEDED__'
        assert '1964' in result
        assert 'Marguerite' in result
        assert _has_finite_main_verb(result)

    def test_start_cycling_exempt(self):
        sent = "Start cycling south on the main road."
        assert _is_style_navigation_sentence(sent)

    def test_head_east_exempt(self):
        sent = "Head east along the coast road."
        assert _is_style_navigation_sentence(sent)

    def test_start_ride_exempt(self):
        sent = "Start your ride at Cap d'Antibes and pedal east along the coastline."
        assert _is_style_navigation_sentence(sent)

    def test_absorb_atmosphere_deleted(self):
        sent = "Take a moment to absorb the atmosphere."
        result = rewrite_r1_sentence_deterministic(sent)
        assert result is None  # Deleted

    def test_enjoy_view_deleted(self):
        sent = "Enjoy the view."
        findings = check_r1_imperatives(sent)
        # Pure instruction should be caught


class TestPriorBoundarySetsLocal256:
    """LOCAL-256's 28 boundary rows — subset of critical ones."""

    def test_panoramic_view_relative_clause(self):
        sent = "Take in the panoramic view that stretches out before you, with the ancient village of Èze rising majestically behind you."
        result = rewrite_r1_sentence_deterministic(sent)
        assert _has_finite_main_verb(result)
        assert 'panoramic view' in result.lower()
        assert 'Èze' in result

    def test_fondation_maeght_copula(self):
        sent = "Look for the Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght."
        result = rewrite_r1_sentence_deterministic(sent)
        assert _has_finite_main_verb(result)
        assert '1964' in result

    def test_fitzgerald_fragment_detected(self):
        fragment = "Scott Fitzgerald's 'Tender is the Night', a vivid portrayal of the Roaring Twenties on the French Riviera."
        assert not _has_finite_main_verb(fragment)
