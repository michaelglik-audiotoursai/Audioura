#!/usr/bin/env python3
"""Test R10 (unfulfilled promise deletion) — labelled set from Michael's Round 2 review.

LOCAL-235: "Either tell us the story or get rid of the sentence!"

A sentence names a subject that requires substantiation (a story, a tale,
history, a legacy) and NEITHER that sentence NOR its neighbours deliver it.
Delivery = a concrete payload: date, named person/event, documented fact.

Labelled set built from RIVIERA_2STOP_ROUND2.md and Michael's Round 2 complaints:
- MUST FIRE: sentences Michael complained about (unfulfilled promises)
- MUST NOT FIRE: his own rewrite prose (concrete facts) and navigation

The look-ahead window is 2 sentences forward + 1 sentence backward.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from style_validator_detector import (
    check_r10_unfulfilled_promise,
    apply_r10_deletions,
    apply_r10_to_description,
    _sentence_has_promise,
    _sentence_has_concrete_payload,
    _split_sentences,
    _is_style_navigation_sentence,
)

# ═══════════════════════════════════════════════════════════════════════════════
# LABELLED SET — from Michael's Round 2 complaints, both directions
# ═══════════════════════════════════════════════════════════════════════════════

# ── MUST FIRE: Michael's Round 2 complaints (unfulfilled promises) ───────────
# These sentences NAME a subject but never deliver on it.
MUST_FIRE = [
    # "each crack and crevice holding a story" — what story?
    "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story.",
    # "The hillsides hold a multitude of tales from a bygone era." — where are the tales?
    "The hillsides hold a multitude of tales from a bygone era.",
    # "serves as a bridge between ancient civilizations and contemporary life"
    "The medieval charm of Eze Village serves as a bridge between ancient civilizations and contemporary life, inviting you to ponder the enduring legacy of those who once walked these very streets.",
    # "a harmonious symphony of past and present"
    "The gentle rustle of the Mediterranean breeze mingles with the distant chime of church bells, creating a harmonious symphony of past and present.",
    # "a testament to the enduring allure"
    "As you cycle onward, remember Eze Village, a testament to the enduring allure of the French Riviera's rich historical tapestry.",
    # "delving into a rich tapestry of history" — no specifics follow
    "Cycling along the shimmering waters, you are not just exploring a physical landscape but also delving into a rich tapestry of history and culture that defines the French Riviera.",
]

# ── MUST NOT FIRE: his own rewrite prose — what good looks like ──────────────
# These sentences deliver concrete payloads.
MUST_NOT_FIRE = [
    # Has date (200 BC) and named place (Èze, Mount Bastide)
    "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
    # Named document (Antonine Itinerary), named place (Avisionis portus)
    "The Antonine Itinerary mentions the bay of Èze as Avisionis portus.",
    # Navigation — always exempt
    "Start cycling south on the main road with the sea on your right until you reach the peninsula's tip with a lighthouse visible in the distance.",
    # Named person (F. Scott Fitzgerald), date (1934), named place (Eden-Roc)
    "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc.",
    # Named place (Hôtel du Cap-Eden-Roc), date (1870)
    "The Hôtel du Cap-Eden-Roc was built here in 1870, at the southern tip of the peninsula.",
    # Named person (Picasso) + named place — concrete delivery
    "At Cap d'Antibes, the tranquil vistas and vibrant atmosphere have inspired artists like Picasso, infusing their work with the essence of this coastal paradise.",
    # Named place (Jardin Exotique) + specific geographic reference
    "At the apex of Jardin Exotique, you can gaze out over the panoramic vista of the Riviera.",
    # Concrete date (1888) + named person (Monet) + named place
    "In January 1888, the renowned artist Claude Monet visited this stunning location during his journey through the south of France.",
    # Measurement (2.7 km) + named places
    "Along this 2.7 km route, you'll traverse rocky cliffs, pass by ancient chapels, and witness the panoramic views of the Lérins Islands to the west and the Mercantour Mountains to the east.",
    # Named place (Villa Eilenroc) — HAS concrete proper noun
    "Look out for the Villa Eilenroc, an opulent mansion surrounded by lush gardens, symbolizing the lavish parties once hosted here by the elite of the 19th century.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — promise detection
# ═══════════════════════════════════════════════════════════════════════════════

def test_promise_detection_must_fire():
    """Every MUST_FIRE sentence should contain a promise-trigger phrase."""
    for sent in MUST_FIRE:
        assert _sentence_has_promise(sent), f"Expected promise trigger in: {sent[:80]}"


def test_promise_detection_some_not_fire_have_no_promise():
    """MUST_NOT_FIRE sentences generally lack promise triggers (or they deliver)."""
    # Navigation and pure facts should not even have promise patterns
    nav_and_facts = [
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
        "The Antonine Itinerary mentions the bay of Èze as Avisionis portus.",
        "Start cycling south on the main road with the sea on your right until you reach the peninsula's tip with a lighthouse visible in the distance.",
        "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc.",
        "The Hôtel du Cap-Eden-Roc was built here in 1870, at the southern tip of the peninsula.",
    ]
    for sent in nav_and_facts:
        # These should either not have a promise trigger, or if they do,
        # they self-deliver (which is tested separately)
        has_promise = _sentence_has_promise(sent)
        if has_promise:
            assert _sentence_has_concrete_payload(sent), \
                f"Has promise but no payload (unexpected): {sent[:80]}"


# ═══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — concrete payload detection
# ═══════════════════════════════════════════════════════════════════════════════

def test_payload_detection_dates_and_names():
    """Sentences with dates, names, and measurements are concrete."""
    concrete = [
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
        "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc.",
        "The Hôtel du Cap-Eden-Roc was built here in 1870, at the southern tip of the peninsula.",
        "Along this 2.7 km route, you'll traverse rocky cliffs.",
        "In January 1888, the renowned artist Claude Monet visited this stunning location.",
    ]
    for sent in concrete:
        assert _sentence_has_concrete_payload(sent), f"Expected concrete payload in: {sent[:80]}"


def test_payload_detection_abstractions_fail():
    """Sentences that are pure abstraction should NOT be concrete."""
    abstract = [
        "The hillsides hold a multitude of tales from a bygone era.",
        "creating a harmonious symphony of past and present.",
        "a testament to the enduring allure of the rich historical tapestry.",
    ]
    for sent in abstract:
        assert not _sentence_has_concrete_payload(sent), \
            f"Unexpected concrete payload in: {sent[:80]}"


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — full R10 check with context
# ═══════════════════════════════════════════════════════════════════════════════

def test_r10_must_fire_isolated():
    """MUST_FIRE sentences should fire R10 when surrounded by other abstractions."""
    for sent in MUST_FIRE:
        # Put it between two other abstract sentences (no delivery around it)
        context = [
            "The atmosphere here is truly remarkable.",
            sent,
            "The air is thick with the scent of the sea.",
        ]
        finding = check_r10_unfulfilled_promise(context, 1)
        assert finding is not None, f"R10 should fire on: {sent[:80]}"
        assert finding['rule_id'] == 'R10_UNFULFILLED_PROMISE'
        assert finding['severity'] == 'error'


def test_r10_must_not_fire_concrete():
    """MUST_NOT_FIRE sentences should never fire R10."""
    for sent in MUST_NOT_FIRE:
        # Even isolated (worst case), concrete sentences must not fire
        context = [
            "The atmosphere here is truly remarkable.",
            sent,
            "The air is thick with the scent of the sea.",
        ]
        finding = check_r10_unfulfilled_promise(context, 1)
        assert finding is None, f"R10 should NOT fire on: {sent[:80]}"


def test_r10_promise_fulfilled_by_next_sentence():
    """A promise followed by delivery in the next sentence should NOT fire."""
    context = [
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story.",
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
        "The views stretch across the bay.",
    ]
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is None, "Promise should be fulfilled by next sentence (200 BC + Mount Bastide)"


def test_r10_promise_fulfilled_by_previous_sentence():
    """A promise preceded by delivery in the previous sentence should NOT fire."""
    context = [
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story.",
        "The views stretch across the bay.",
    ]
    finding = check_r10_unfulfilled_promise(context, 1)
    assert finding is None, "Promise should be fulfilled by previous sentence (200 BC + Mount Bastide)"


def test_r10_promise_not_fulfilled_by_distant_sentence():
    """A promise with delivery only 3+ sentences away should fire."""
    context = [
        "The hillsides hold a multitude of tales from a bygone era.",
        "The atmosphere is serene and peaceful.",
        "The gentle breeze carries memories.",
        "In 1200, the Saracens built the first watchtower here.",
    ]
    # Delivery is at index 3 — beyond the lookahead of 2
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is not None, "Promise should NOT be fulfilled by sentence 3+ away"


def test_r10_navigation_exempt():
    """Navigation sentences are never deleted by R10."""
    context = [
        "Start cycling south on the main road with the sea on your right.",
        "The breeze is gentle here.",
    ]
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is None, "Navigation must be exempt from R10"


# ═══════════════════════════════════════════════════════════════════════════════
# DELETION INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_apply_r10_deletions_removes_unfulfilled():
    """apply_r10_deletions should remove unfulfilled promises."""
    para = (
        "The hillsides hold a multitude of tales from a bygone era. "
        "The gentle breeze carries the scent of lavender."
    )
    result = apply_r10_deletions(para)
    assert "multitude of tales" not in result
    # The second sentence (no promise) should survive
    assert "lavender" in result


def test_apply_r10_deletions_keeps_fulfilled():
    """apply_r10_deletions should keep promises that are fulfilled by neighbours."""
    para = (
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story. "
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide."
    )
    result = apply_r10_deletions(para)
    # Both sentences should survive — the promise is fulfilled by the next sentence
    assert "holding a story" in result
    assert "200 BC" in result


def test_apply_r10_to_description_cross_paragraph():
    """R10 should use next paragraph's sentences for look-ahead."""
    desc = (
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story.\n\n"
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide."
    )
    result, deleted, emptied = apply_r10_to_description(desc)
    # The promise in paragraph 1 is fulfilled by paragraph 2's first sentence
    assert "holding a story" in result
    assert deleted == 0


def test_apply_r10_to_description_empties_paragraph():
    """R10 should empty a paragraph if all its sentences are unfulfilled promises."""
    desc = (
        "The hillsides hold a multitude of tales from a bygone era. "
        "The walls whisper tales of a bygone world.\n\n"
        "The gentle breeze carries the scent of lavender."
    )
    result, deleted, emptied = apply_r10_to_description(desc)
    assert "multitude of tales" not in result
    assert "lavender" in result
    assert deleted >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# REGRESSION — R9 labelled set must still pass
# ═══════════════════════════════════════════════════════════════════════════════

def test_r10_does_not_fire_on_r9_must_not_fire():
    """R10 must not fire on sentences that R9's labelled set protects."""
    from style_validator_detector import check_r9_generic

    # These sentences from R9's MUST_NOT_FIRE contain proper nouns/dates
    # and should not be touched by R10 either
    r9_protected = [
        "Start biking southeast on the main road, continue straight until you reach the roundabout near the coast.",
        "Villefranche-sur-Mer, known as the \"Free City on Sea,\" has ancient streets that exude a timeless charm.",
        "The town's strategic location east of Nice and southwest of Monaco has been pivotal in its history.",
        "The deep bay of Villefranche provides secure anchorage for ships, with depths reaching 320 feet, a natural wonder in the Mediterranean.",
        "In January 1888, the renowned artist Claude Monet visited this stunning location during his journey through the south of France.",
    ]
    for sent in r9_protected:
        context = ["Something abstract.", sent, "Something else abstract."]
        finding = check_r10_unfulfilled_promise(context, 1)
        assert finding is None, f"R10 must NOT fire on R9-protected: {sent[:60]}"


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

def test_r10_short_sentences_exempt():
    """Very short sentences should not be checked."""
    context = ["A tale.", "Next sentence."]
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is None


def test_r10_self_delivering_sentence():
    """A sentence that both promises and delivers should NOT fire."""
    context = [
        "The walls hold stories of the 13th-century siege when Saracen raiders attacked the village.",
        "The breeze is gentle.",
    ]
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is None, "Self-delivering promise must not fire"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
