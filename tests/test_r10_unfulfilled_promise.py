#!/usr/bin/env python3
"""Test R10 (unfulfilled promise deletion) — labelled set from Michael's Round 2 review.

LOCAL-235: "Either tell us the story or get rid of the sentence!"

A sentence names a subject that requires substantiation (a story, a tale,
history, a legacy) and NEITHER that sentence NOR its neighbours deliver it
ON THE SAME TOPIC. Delivery = a concrete payload: date, named person/event,
documented fact — that is ABOUT the subject promised.

CRITICAL (R2 bounce fix): The labelled set is built from REAL PARAGRAPHS
verbatim from tours 163 and 180, NOT isolated sentences in synthetic context.
Every MUST_FIRE case fires IN ITS OWN PARAGRAPH.

Look-ahead window: 2 sentences forward + 1 sentence backward.
Topic overlap required: delivery must share content words with the promise.
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
    _extract_content_words,
    _delivery_matches_promise,
    _sentence_has_structural_promise,
)

# ═══════════════════════════════════════════════════════════════════════════════
# REAL PARAGRAPHS — verbatim from tour 180 (RIVIERA_2STOP_ROUND2.md)
# These are what LEAD tested against and found the original R10 produced [].
# ═══════════════════════════════════════════════════════════════════════════════

# Paragraph 5 from tour 180 (Eze Village stop), verbatim
EZE_PARAGRAPH_5 = (
    "In 200 BC, the area surrounding Èze saw its first inhabitants settle near "
    "Mount Bastide. The Antonine Itinerary mentions the bay of Èze as Avisionis "
    "portus, highlighting its maritime significance in antiquity. The timeless "
    "allure of Eze Village resides in its ability to transport visitors back "
    "through the annals of time. The aged stone walls exude a palpable sense of "
    "antiquity, each crack and crevice holding a story. The gentle rustle of the "
    "Mediterranean breeze mingles with the distant chime of church bells, "
    "creating a harmonious symphony of past and present. Wandering through the "
    "narrow alleyways, you'll encounter artisanal workshops where local craftsmen "
    "keep age-old traditions alive, infusing modernity with a touch of history. "
    "As you pause to admire the intricate ironwork adorning centuries-old doors, "
    "the connection between past and present becomes tangible, a thread weaving "
    "through the fabric of time. This stop on the French Riviera cycling tour "
    "offers a profound glimpse into the enduring spirit of a village steeped in "
    "history. The medieval charm of Eze Village serves as a bridge between ancient "
    "civilizations and contemporary life, inviting you to ponder the enduring "
    "legacy of those who once walked these very streets. At the apex of Jardin "
    "Exotique, you can gaze out over the panoramic vista of the Riviera. The "
    "hillsides hold a multitude of tales from a bygone era. As you cycle onward, "
    "remember Eze Village, a testament to the enduring allure of the French "
    "Riviera's rich historical tapestry."
)

# Paragraph 3 from tour 180 (Cap d'Antibes stop), verbatim
CAP_PARAGRAPH_3 = (
    "Cap d'Antibes, situated on the French Riviera, holds a special place in "
    "the region's history and culture. This cape, along with Cap Ferrat to the "
    "northeast, forms a significant feature of the landscape, housing prestigious "
    "establishments like the Hôtel du Cap-Eden-Roc and Grand-Hôtel du Cap-Ferrat. "
    "These iconic hotels are renowned for their exclusivity and luxury, attracting "
    "visitors from around the world. In the literary world, Cap d'Antibes has "
    "inspired notable works, including F. Scott Fitzgerald's novel \"Tender Is the "
    "Night.\" This masterpiece captures the essence of the French Riviera during "
    "the Jazz Age, depicting the poignant tale of Dick Diver and his wife, Nicole, "
    "against the backdrop of this enchanting coastal setting. The breathtaking "
    "sentier Littoral is a scenic coastal path nearly 3.5 kilometers long. It "
    "begins at plage de la Garoupe and culminates at Cap d'Antibes near Villa "
    "Eilenroc. The trail offers stunning views of the coastline, allowing visitors "
    "to appreciate the natural beauty of the surroundings. At Cap d'Antibes, the "
    "tranquil vistas and vibrant atmosphere have inspired artists like Picasso, "
    "infusing their work with the essence of this coastal paradise. Cycling along "
    "the shimmering waters, you are not just exploring a physical landscape but "
    "also delving into a rich tapestry of history and culture that defines the "
    "French Riviera. The mystical allure of Eze Village beckons you forward, "
    "promising more wonders and discoveries along your journey."
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
    # Named place (Villa Eilenroc) + date (19th century)
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
    nav_and_facts = [
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
        "The Antonine Itinerary mentions the bay of Èze as Avisionis portus.",
        "Start cycling south on the main road with the sea on your right until you reach the peninsula's tip with a lighthouse visible in the distance.",
        "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc.",
        "The Hôtel du Cap-Eden-Roc was built here in 1870, at the southern tip of the peninsula.",
    ]
    for sent in nav_and_facts:
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
# UNIT TESTS — topic-aware delivery matching
# ═══════════════════════════════════════════════════════════════════════════════

def test_delivery_matches_same_subject():
    """Delivery about the same subject (walls) matches the promise."""
    promise = "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story."
    delivery = "These walls were built in 1388 when the village was fortified against Saracen raids."
    assert _delivery_matches_promise(promise, delivery), \
        "Delivery about walls should match promise about walls"


def test_delivery_does_not_match_different_subject():
    """Delivery about Èze settlers does NOT match promise about stone walls."""
    promise = "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story."
    delivery = "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide."
    assert not _delivery_matches_promise(promise, delivery), \
        "Delivery about Èze settlers should NOT match promise about stone walls"


def test_delivery_matches_hillside_topic():
    """Delivery about the hillsides matches promise about hillsides."""
    promise = "The hillsides hold a multitude of tales from a bygone era."
    delivery = "These hillsides were terraced in the 14th century for olive cultivation by Benedictine monks."
    assert _delivery_matches_promise(promise, delivery), \
        "Delivery about hillsides should match promise about hillsides"


def test_delivery_matches_village_topic():
    """Delivery mentioning village/Eze matches promise about Eze Village."""
    promise = "The medieval charm of Eze Village serves as a bridge between ancient civilizations and contemporary life."
    delivery = "The village was fortified in 1388 by the House of Savoy to protect against coastal raiders."
    assert _delivery_matches_promise(promise, delivery), \
        "Delivery about the village should match promise about Eze Village"


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — REAL PARAGRAPHS from tours 163/180
# LEAD's core requirement: "Every one of Michael's five complaints must fire
# IN ITS OWN PARAGRAPH."
# ═══════════════════════════════════════════════════════════════════════════════

def test_r10_fires_in_real_eze_paragraph():
    """R10 must fire on Michael's complaints within the REAL Eze paragraph.

    This is THE critical test from LEAD's bounce. The previous implementation
    returned [] for this paragraph because "In 200 BC" was treated as delivery
    for "stone walls holding a story" — but they're about different subjects.
    """
    sentences = _split_sentences(EZE_PARAGRAPH_5)

    # Find the complaint sentences and verify they fire
    must_fire_fragments = [
        "each crack and crevice holding a story",
        "multitude of tales from a bygone era",
        "bridge between ancient civilizations",
        "harmonious symphony of past and present",
        "testament to the enduring allure",
    ]

    fired_fragments = set()
    for i, sent in enumerate(sentences):
        finding = check_r10_unfulfilled_promise(sentences, i)
        if finding:
            for frag in must_fire_fragments:
                if frag in finding['sentence']:
                    fired_fragments.add(frag)

    missing = [f for f in must_fire_fragments if f not in fired_fragments]
    assert len(missing) == 0, (
        f"R10 failed to fire in the real Eze paragraph on these fragments: {missing}"
    )


def test_r10_fires_in_real_cap_paragraph():
    """R10 must fire on the 'rich tapestry' sentence in the real Cap paragraph."""
    sentences = _split_sentences(CAP_PARAGRAPH_3)

    fired = False
    for i, sent in enumerate(sentences):
        finding = check_r10_unfulfilled_promise(sentences, i)
        if finding and "rich tapestry" in finding['sentence']:
            fired = True
            break

    assert fired, "R10 must fire on 'delving into a rich tapestry' in the real Cap paragraph"


def test_r10_does_not_fire_on_concrete_sentences_in_real_paragraph():
    """Concrete sentences (dates, names) in the real paragraph must NOT fire."""
    sentences = _split_sentences(EZE_PARAGRAPH_5)

    # These are the concrete sentences that must survive
    concrete_fragments = [
        "In 200 BC",
        "Antonine Itinerary",
        "Jardin Exotique",
    ]

    for i, sent in enumerate(sentences):
        finding = check_r10_unfulfilled_promise(sentences, i)
        if finding:
            for frag in concrete_fragments:
                assert frag not in finding['sentence'], (
                    f"R10 must NOT fire on concrete sentence containing '{frag}': "
                    f"{finding['sentence'][:80]}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# FALSIFICATION TESTS — proves the delivery check does something
# LEAD requirement: "take a paragraph where R10 fires, append a sentence that
# genuinely delivers the promise, assert R10 stops firing."
# ═══════════════════════════════════════════════════════════════════════════════

def test_falsification_walls_story_delivered():
    """When 'walls holding a story' is followed by a wall-specific fact, R10 stops firing."""
    # Promise fires in isolation
    sentences_without = [
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story.",
        "The gentle breeze carries the scent of lavender.",
        "The views are breathtaking from here.",
    ]
    finding = check_r10_unfulfilled_promise(sentences_without, 0)
    assert finding is not None, "Sanity: R10 should fire without on-topic delivery"

    # Now add a sentence that genuinely delivers about the WALLS
    sentences_with = [
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story.",
        "These fortification walls were erected in 1388 by the House of Savoy after Saracen raids devastated the original settlement.",
        "The views are breathtaking from here.",
    ]
    finding = check_r10_unfulfilled_promise(sentences_with, 0)
    assert finding is None, (
        "R10 should STOP firing when a wall-specific delivery follows: "
        "'walls erected in 1388 by House of Savoy' delivers 'walls holding a story'"
    )


def test_falsification_hillsides_tales_delivered():
    """When 'hillsides hold tales' is followed by a hillside-specific fact, R10 stops firing."""
    sentences_without = [
        "The hillsides hold a multitude of tales from a bygone era.",
        "The sea sparkles in the distance.",
        "Visitors come from around the world.",
    ]
    finding = check_r10_unfulfilled_promise(sentences_without, 0)
    assert finding is not None, "Sanity: R10 should fire without on-topic delivery"

    sentences_with = [
        "The hillsides hold a multitude of tales from a bygone era.",
        "These hillsides were terraced in the 14th century for olive cultivation by Benedictine monks from the Lérins abbey.",
        "The sea sparkles in the distance.",
    ]
    finding = check_r10_unfulfilled_promise(sentences_with, 0)
    assert finding is None, (
        "R10 should STOP firing when a hillside-specific delivery follows"
    )


def test_falsification_bridge_between_civilizations_delivered():
    """When 'bridge between ancient civilizations' is followed by a civilization-specific fact, R10 stops."""
    sentences_without = [
        "The medieval charm of Eze Village serves as a bridge between ancient civilizations and contemporary life.",
        "The atmosphere is serene and peaceful.",
        "The views from above are stunning.",
    ]
    finding = check_r10_unfulfilled_promise(sentences_without, 0)
    assert finding is not None, "Sanity: R10 should fire without on-topic delivery"

    sentences_with = [
        "The medieval charm of Eze Village serves as a bridge between ancient civilizations and contemporary life.",
        "The village was founded as a Ligurian settlement in 600 BC, conquered by Romans in 154 BC, fortified by Saracens in the 9th century, and rebuilt under Savoyard rule in 1388.",
        "The atmosphere is serene and peaceful.",
    ]
    finding = check_r10_unfulfilled_promise(sentences_with, 0)
    assert finding is None, (
        "R10 should STOP firing when a village-civilization-specific delivery follows"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MUST NOT FIRE — concrete sentences never fire
# ═══════════════════════════════════════════════════════════════════════════════

def test_r10_must_not_fire_concrete():
    """MUST_NOT_FIRE sentences should never fire R10, even in worst-case context."""
    for sent in MUST_NOT_FIRE:
        # Even isolated between two abstractions — concrete sentences must not fire
        context = [
            "The atmosphere here is truly remarkable.",
            sent,
            "The air is thick with the scent of the sea.",
        ]
        finding = check_r10_unfulfilled_promise(context, 1)
        assert finding is None, f"R10 should NOT fire on: {sent[:80]}"


# ═══════════════════════════════════════════════════════════════════════════════
# PROMISE + SELF-DELIVERY
# ═══════════════════════════════════════════════════════════════════════════════

def test_r10_self_delivering_sentence():
    """A sentence that both promises and delivers should NOT fire."""
    context = [
        "The walls hold stories of the 13th-century siege when Saracen raiders attacked the village.",
        "The breeze is gentle.",
    ]
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is None, "Self-delivering promise must not fire"


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

def test_r10_short_sentences_exempt():
    """Very short sentences should not be checked."""
    context = ["A tale.", "Next sentence here."]
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is None


def test_r10_navigation_exempt():
    """Navigation sentences are never deleted by R10."""
    context = [
        "Start cycling south on the main road with the sea on your right.",
        "The breeze is gentle here.",
    ]
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is None, "Navigation must be exempt from R10"


def test_r10_promise_not_fulfilled_by_distant_sentence():
    """A promise with delivery only 3+ sentences away should fire."""
    context = [
        "The hillsides hold a multitude of tales from a bygone era.",
        "The atmosphere is serene and peaceful.",
        "The gentle breeze carries memories.",
        "These hillsides were terraced in the 14th century for olive cultivation.",
    ]
    # Delivery is at index 3 — beyond the lookahead of 2
    finding = check_r10_unfulfilled_promise(context, 0)
    assert finding is not None, "Promise should NOT be fulfilled by sentence 3+ away"


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


def test_apply_r10_deletions_keeps_on_topic_delivery():
    """apply_r10_deletions should keep promises fulfilled by on-topic neighbours."""
    para = (
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story. "
        "These fortification walls were erected in 1388 by the House of Savoy."
    )
    result = apply_r10_deletions(para)
    # Both sentences should survive — the promise is fulfilled by on-topic delivery
    assert "holding a story" in result
    assert "1388" in result


def test_apply_r10_deletions_removes_off_topic_delivery():
    """apply_r10_deletions should DELETE promise when nearby delivery is off-topic."""
    para = (
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide. "
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story. "
        "The gentle rustle of the Mediterranean breeze mingles with the distant chime of church bells, "
        "creating a harmonious symphony of past and present."
    )
    result = apply_r10_deletions(para)
    # The 200 BC sentence should survive (no promise)
    assert "200 BC" in result
    # The promise sentences should be DELETED (off-topic delivery)
    assert "holding a story" not in result
    assert "symphony of past and present" not in result


def test_apply_r10_to_description_cross_paragraph():
    """R10 should use next paragraph's sentences for on-topic look-ahead."""
    desc = (
        "The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story.\n\n"
        "These walls were built in 1388 when the village was fortified against Saracen raiders."
    )
    result, deleted, emptied = apply_r10_to_description(desc)
    # The promise in paragraph 1 is fulfilled by paragraph 2's ON-TOPIC sentence
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
    # These sentences from R9's MUST_NOT_FIRE contain proper nouns/dates
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
# CONTENT WORD EXTRACTION (topic matching internals)
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_content_words_filters_stopwords():
    """Content words should exclude stopwords and abstract fillers."""
    words = _extract_content_words("The aged stone walls exude a palpable sense of antiquity")
    assert "the" not in words
    assert "aged" in words
    assert "stone" in words
    assert "walls" in words
    assert "exude" in words
    # "sense" is in abstract fillers — but "palpable" is OK (it's a modifier)
    assert "palpable" in words or "sense" in words  # at least one retained
    # Key: stopwords are gone
    words2 = _extract_content_words("The history of this place is truly remarkable")
    assert "history" not in words2  # abstract filler
    assert "the" not in words2     # stopword


def test_extract_content_words_from_concrete():
    """Concrete sentences should produce grounding content words."""
    words = _extract_content_words("In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.")
    assert "èze" in words or "eze" in words  # Unicode normalization
    assert "inhabitants" in words
    assert "settle" in words
    assert "mount" in words
    assert "bastide" in words


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL-240: Round 3 labelled set — widened structural detection
# ═══════════════════════════════════════════════════════════════════════════════

ROUND3_PARAGRAPH_3 = (
    "You are about to embark on a journey through the French Riviera, where "
    "the sun-drenched coasts and ancient villages hold a tapestry woven with "
    "the glamour of modern allure and whispers of medieval roots. Cycling "
    "through winding paths, you'll discover a blend of architectural marvels "
    "and forgotten tales that shape its identity. The ancient fortifications "
    "of the Garoupe Lighthouse stand sentinel against opulent villas, "
    "revealing a juxtaposition of past and present. Discover how the idyllic "
    "beauty of the French Riviera masks the secrets of its past as you "
    "unravel its intricate story through each chapter of this enchanting "
    "journey."
)

# ── MUST FIRE: Round 3 unfulfilled promises ──────────────────────────────────
ROUND3_MUST_FIRE_FRAGMENTS = [
    "villages hold a tapestry woven with",
    "forgotten tales that shape its identity",
    "masks the secrets of its past",
    "its intricate story through each chapter",
    "stand sentinel against opulent villas, revealing a juxtaposition of past and present",
]

# ── MUST NOT FIRE: Michael's rewrite prose ───────────────────────────────────
ROUND3_MUST_NOT_FIRE = [
    "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
    "The Antonine Itinerary mentions the bay of Èze as Avisionis portus.",
    "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc.",
    "…the Hôtel du Cap-Eden-Roc, built here in 1870, at the southern tip.",
    "Start cycling south on the main road…",
]


def test_r10_round3_all_five_promises_fire():
    """LOCAL-240: All five promise fragments from Round 3 Para 3 must fire."""
    sentences = _split_sentences(ROUND3_PARAGRAPH_3)

    fired_sentences = []
    for i in range(len(sentences)):
        finding = check_r10_unfulfilled_promise(sentences, i)
        if finding:
            fired_sentences.append(finding['sentence'])

    for frag in ROUND3_MUST_FIRE_FRAGMENTS:
        found = any(frag in s for s in fired_sentences)
        assert found, f"R10 must fire on round-3 fragment: '{frag[:60]}'"


def test_r10_round3_rewrite_prose_stays_clean():
    """LOCAL-240: Michael's rewrite prose must NOT fire R10."""
    for sent in ROUND3_MUST_NOT_FIRE:
        context = ["The atmosphere here is remarkable.", sent, "The air carries memories."]
        finding = check_r10_unfulfilled_promise(context, 1)
        assert finding is None, f"R10 must NOT fire on rewrite: '{sent[:60]}'"


def test_r10_structural_detection_is_additive():
    """LOCAL-240: structural detection adds new catches without breaking existing."""
    from style_validator_detector import _sentence_has_structural_promise

    # These should trigger structural detection (noun + verb of possession/concealment)
    structural_triggers = [
        "ancient villages hold a tapestry woven with the glamour of modern allure",
        "forgotten tales that shape its identity",
        "masks the secrets of its past",
        "stand sentinel against opulent villas, revealing a juxtaposition of past and present",
    ]
    for s in structural_triggers:
        assert _sentence_has_structural_promise(s), \
            f"Structural detection should trigger on: '{s[:60]}'"

    # These should NOT trigger structural detection (no promise noun or no promise verb)
    structural_safe = [
        "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide.",
        "The Antonine Itinerary mentions the bay of Èze as Avisionis portus.",
        "Start cycling south on the main road with the sea on your right.",
        "The Hôtel du Cap-Eden-Roc was built here in 1870.",
    ]
    for s in structural_safe:
        assert not _sentence_has_structural_promise(s), \
            f"Structural detection should NOT trigger on: '{s[:60]}'"
