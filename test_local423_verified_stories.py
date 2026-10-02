"""LOCAL-423: Test that story verification gates delivery — unsourced claims are rejected.

Tests bind to PRODUCTION call sites:
  - story_verifier.verify_story_candidate (called from generate_tour_text.py after story gate)
  - story_verifier.extract_claims (claim extraction used in verify_story_candidate)
  - story_verifier.disambiguate_snippets (entity disambiguation in verify_story_candidate)
  - story_verifier.detect_self_contradictions (contradiction check in verify_story_candidate)
  - generate_tour_text.build_snippet_block (injects VERIFICATION CONSTRAINT into LLM prompt)

Fails on `storied` (no story_verifier.py, no VERIFICATION CONSTRAINT in build_snippet_block).
Passes with the LOCAL-423 fix.

Acceptance bar (Michael, 2026-08-11):
  - Every factual claim maps to a retrieved source URL
  - A claim with no source must not ship
  - Show at least one candidate story the verifier rejected, and why
  - No self-contradiction: "15 lithographs" and "40 lithographs" must be impossible
  - Fridman is named and NOT described as Boston-based (unless sourced)
  - Entity disambiguation: the linguist and the gallery are excluded
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from story_verifier import (
    verify_story_candidate,
    extract_claims,
    disambiguate_snippets,
    disambiguate_snippet,
    detect_self_contradictions,
    Claim,
)
from generate_tour_text import build_snippet_block


# ─── Fixture: corpus snippets from MFA Unbound stop 1 (the 67 we hold) ───

STOP1_SNIPPETS = [
    {
        'title': 'Le Lézard aux plumes d\'or — MFA Collection',
        'snippet': 'Joan Miró. Le Lézard aux plumes d\'or (The Lizard with Golden Feathers). '
                   '1971. Portfolio of 12 lithographs (including cover) on Arches wove paper. '
                   'Published by Louis Broder, Paris. Printed by Mourlot, Paris.',
        'url': 'https://collections.mfa.org/objects/12345',
    },
    {
        'title': 'artfocusnow.com — Collector Profile',
        'snippet': 'Boris Fridman, a Russian collector, donated several important livres '
                   'd\'artiste to the Museum of Fine Arts, Boston. His collection included '
                   'works by Miró, Chagall, and Picasso.',
        'url': 'https://artfocusnow.com/fridman-profile',
    },
    {
        'title': 'Louis Broder Publisher — Livres d\'artiste',
        'snippet': 'Louis Broder was a Parisian publisher who specialized in luxury limited '
                   'editions of livres d\'artiste. He commissioned works from Miró, Braque, '
                   'and other School of Paris artists.',
        'url': 'https://example.com/broder-publisher',
    },
    {
        'title': 'Mourlot Workshop History',
        'snippet': 'Mourlot Frères was a lithography workshop in Paris founded in 1852. '
                   'Located on Rue de Chabrol, the atelier became the primary printer for '
                   'School of Paris artists including Picasso, Miró, and Chagall.',
        'url': 'https://example.com/mourlot-history',
    },
    {
        'title': 'Christie\'s Auction Record — Miró 1967',
        'snippet': 'Joan Miró. Lithograph in colours, 1967, on wove paper watermark Miró, '
                   'from the set of 18, signed in pencil. Estimate: $8,000-12,000.',
        'url': 'https://christies.com/lot/miro-1967',
    },
]

# Fridman disambiguation: wrong entities
FRIDMAN_LINGUIST_SNIPPET = {
    'title': 'Boris Fridman-Mintz — UNAM',
    'snippet': 'Boris Fridman-Mintz is a linguist at UNAM (Mexico City) specializing in '
               'deaf community studies and sign language research in Mexico.',
    'url': 'https://unam.mx/fridman-mintz',
}

FRIDMAN_GALLERY_SNIPPET = {
    'title': 'Fridman Gallery — New York',
    'snippet': 'Fridman Gallery is a contemporary art gallery in New York, founded in 2013. '
               'It presents emerging and mid-career artists working across media.',
    'url': 'https://fridmangallery.com/about',
}


# ─── Fixture: the FAILING text Michael identified (421's output) ───

STOP1_UNSOURCED_STORY = (
    "Boris Fridman, a Boston-based collector who assembled one of the largest "
    "private holdings of livres d'artiste in New England, donated this work to "
    "the MFA in 2003. Broder's editions were tiny — rarely exceeding 150 copies — "
    "and he insisted on direct collaboration between artist, poet, and printer. "
    "Mourlot's workshop was one of the few in Europe equipped for chromolithography "
    "at this scale, which enabled the livre d'artiste tradition to revive after the war."
)

# The same story but with ONLY sourced claims
STOP1_SOURCED_STORY = (
    "Boris Fridman, a Russian collector, donated several important livres d'artiste "
    "to the Museum of Fine Arts, Boston. Louis Broder was a Parisian publisher who "
    "commissioned works from Miró as part of his specialization in luxury limited "
    "editions. Mourlot Frères, founded in 1852 on Rue de Chabrol in Paris, printed "
    "this portfolio of 12 lithographs on Arches wove paper."
)

# Self-contradicting story (the lithograph-count bug)
STOP1_CONTRADICTING_STORY = (
    "This portfolio contains 15 lithographs printed by Mourlot Frères in Paris. "
    "Louis Broder published the edition, which features 40 color lithographs by Miró. "
    "Boris Fridman, a Russian collector, donated this work to the MFA."
)

STOP1_CREDIT_LINE = (
    "Gift of Boris Fridman. Published by Louis Broder. "
    "Printed by Mourlot Frères. Lithographs on Arches paper, 1971."
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: verify_story_candidate rejects unsourced claims
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerifyStoryCandidate:
    """Bind to: story_verifier.verify_story_candidate
    (called from generate_tour_text.py LOCAL-423 verification block)."""

    def test_sourced_story_passes(self):
        """A story where every claim traces to a snippet passes verification."""
        result = verify_story_candidate(
            story_text=STOP1_SOURCED_STORY,
            snippets=STOP1_SNIPPETS,
            credit_line=STOP1_CREDIT_LINE,
            stop_name="Stop 1",
        )
        assert result['passed'], (
            f"Should pass: all claims sourced. "
            f"Unsourced: {result['unsourced_details']}"
        )
        assert result['claims_sourced'] > 0
        assert result['claims_unsourced'] == 0

    def test_unsourced_story_fails(self):
        """Michael's marked-wrong story (Boston-based, 2003, 150 copies) fails."""
        result = verify_story_candidate(
            story_text=STOP1_UNSOURCED_STORY,
            snippets=STOP1_SNIPPETS,
            credit_line=STOP1_CREDIT_LINE,
            stop_name="Stop 1",
        )
        assert not result['passed'], (
            "Should FAIL: claims 'Boston-based', '2003', '150 copies' have no source"
        )
        assert result['claims_unsourced'] > 0
        # Check specific unsourced claims
        unsourced_texts = [d['text'].lower() for d in result['unsourced_details']]
        # At least one of these invented claims should be caught
        has_boston = any('boston' in t for t in unsourced_texts)
        has_year = any('2003' in t for t in unsourced_texts)
        has_150 = any('150' in t for t in unsourced_texts)
        assert has_boston or has_year or has_150, (
            f"Expected to catch 'Boston-based' or '2003' or '150 copies'. "
            f"Got: {unsourced_texts}"
        )

    def test_self_contradicting_story_fails(self):
        """'15 lithographs' + '40 color lithographs' = automatic rejection."""
        result = verify_story_candidate(
            story_text=STOP1_CONTRADICTING_STORY,
            snippets=STOP1_SNIPPETS,
            credit_line=STOP1_CREDIT_LINE,
            stop_name="Stop 1",
        )
        assert not result['passed'], "Should FAIL: 15 vs 40 lithographs is a contradiction"
        assert result['claims_contradicted'] > 0 or result['claims_unsourced'] > 0
        # The contradiction should be detected
        if result['contradictions']:
            contradiction_text = str(result['contradictions'])
            assert '15' in contradiction_text or '40' in contradiction_text


# ═══════════════════════════════════════════════════════════════════════════════
# Test: entity disambiguation excludes wrong entities
# ═══════════════════════════════════════════════════════════════════════════════

class TestEntityDisambiguation:
    """Bind to: story_verifier.disambiguate_snippets
    (called within verify_story_candidate for entity filtering)."""

    def test_linguist_excluded(self):
        """Boris Fridman-Mintz (linguist in Mexico) is excluded."""
        is_valid, reason = disambiguate_snippet(
            snippet_text=FRIDMAN_LINGUIST_SNIPPET['snippet'],
            snippet_title=FRIDMAN_LINGUIST_SNIPPET['title'],
            target_surname='Fridman',
        )
        assert not is_valid, "Should exclude: Fridman-Mintz is a linguist, not the collector"
        assert 'linguist' in reason.lower() or 'wrong person' in reason.lower()

    def test_gallery_excluded(self):
        """Fridman Gallery (NYC, 2013) is excluded."""
        is_valid, reason = disambiguate_snippet(
            snippet_text=FRIDMAN_GALLERY_SNIPPET['snippet'],
            snippet_title=FRIDMAN_GALLERY_SNIPPET['title'],
            target_surname='Fridman',
        )
        assert not is_valid, "Should exclude: Fridman Gallery is unrelated to collector"
        assert 'gallery' in reason.lower() or 'wrong entity' in reason.lower()

    def test_real_collector_kept(self):
        """The actual Boris Fridman collector snippet is kept."""
        is_valid, reason = disambiguate_snippet(
            snippet_text=STOP1_SNIPPETS[1]['snippet'],
            snippet_title=STOP1_SNIPPETS[1]['title'],
            target_surname='Fridman',
        )
        assert is_valid, f"Should keep: this IS the collector Boris Fridman. Reason: {reason}"

    def test_batch_disambiguation(self):
        """disambiguate_snippets filters out wrong entities from a batch."""
        all_snippets = STOP1_SNIPPETS + [FRIDMAN_LINGUIST_SNIPPET, FRIDMAN_GALLERY_SNIPPET]
        valid, excluded = disambiguate_snippets(all_snippets, 'Fridman')
        assert len(excluded) == 2, f"Should exclude 2 (linguist + gallery), got {len(excluded)}"
        assert len(valid) == len(STOP1_SNIPPETS)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: self-contradiction detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestSelfContradiction:
    """Bind to: story_verifier.detect_self_contradictions
    (called within verify_claims_against_corpus)."""

    def test_contradicting_lithograph_counts(self):
        """15 lithographs + 40 lithographs in same text = contradiction."""
        claims = extract_claims(STOP1_CONTRADICTING_STORY)
        contradictions = detect_self_contradictions(claims)
        assert len(contradictions) > 0, (
            "Should detect contradiction: 15 vs 40 lithographs"
        )
        # Verify the specific numbers are caught
        nums = set()
        for c1, c2, _ in contradictions:
            nums.add(c1.value)
            nums.add(c2.value)
        assert '15' in nums and '40' in nums

    def test_consistent_numbers_no_contradiction(self):
        """Same number repeated = no contradiction."""
        text = "The portfolio of 12 lithographs was published in 1971. All 12 lithographs are on Arches paper."
        claims = extract_claims(text)
        contradictions = detect_self_contradictions(claims)
        assert len(contradictions) == 0, "Same number (12) repeated is not a contradiction"

    def test_different_subjects_no_contradiction(self):
        """Different subjects with different numbers = no contradiction."""
        text = "The set contains 10 drypoints and 5 etchings on sheepskin."
        claims = extract_claims(text)
        contradictions = detect_self_contradictions(claims)
        assert len(contradictions) == 0, "10 drypoints + 5 etchings = different subjects"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: claim extraction finds the right claims
# ═══════════════════════════════════════════════════════════════════════════════

class TestClaimExtraction:
    """Bind to: story_verifier.extract_claims (called within verify_story_candidate)."""

    def test_extracts_numeric_claims(self):
        """Numeric claims like '150 copies' are extracted."""
        claims = extract_claims("Broder's editions rarely exceeded 150 copies.")
        numeric = [c for c in claims if c.claim_type == 'numeric']
        assert len(numeric) >= 1
        assert any(c.value == '150' for c in numeric)

    def test_extracts_year_claims(self):
        """Year claims like 'donated in 2003' are extracted."""
        claims = extract_claims("Fridman donated this work to the MFA in 2003.")
        year_claims = [c for c in claims if c.claim_type in ('year', 'donation_date')]
        assert len(year_claims) >= 1
        assert any(c.value == '2003' for c in year_claims)

    def test_extracts_location_descriptor(self):
        """Location descriptors like 'Boston-based' are extracted."""
        claims = extract_claims("Boris Fridman, a Boston-based collector, donated this work.")
        loc_claims = [c for c in claims if c.claim_type == 'location_descriptor']
        assert len(loc_claims) >= 1
        assert any('boston' in c.value.lower() for c in loc_claims)

    def test_empty_text_no_claims(self):
        """Empty text yields no claims."""
        claims = extract_claims("")
        assert len(claims) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test: build_snippet_block includes VERIFICATION CONSTRAINT
# ═══════════════════════════════════════════════════════════════════════════════

class TestSnippetBlockVerificationConstraint:
    """Bind to: generate_tour_text.build_snippet_block (called at line 9253).
    Goes RED on `storied` (no VERIFICATION CONSTRAINT), GREEN with LOCAL-423."""

    def test_snippet_block_contains_verification_constraint(self):
        """build_snippet_block must inject the LOCAL-423 verification constraint."""
        snippets = [
            {'title': 'Test', 'snippet': 'Test snippet about Boris Fridman', 'url': ''},
        ]
        block = build_snippet_block(snippets, artist='Joan Miró', specifics=[])
        assert 'VERIFICATION CONSTRAINT' in block, (
            "build_snippet_block must contain 'VERIFICATION CONSTRAINT' (LOCAL-423)"
        )
        assert 'LOCAL-423' in block, (
            "build_snippet_block must reference LOCAL-423"
        )
        assert 'STRIPPED' in block or 'stripped' in block, (
            "Verification constraint must warn that unsourced claims will be stripped"
        )

    def test_snippet_block_warns_about_self_contradiction(self):
        """build_snippet_block must warn about self-contradiction rejection."""
        snippets = [
            {'title': 'Test', 'snippet': 'Test snippet', 'url': ''},
        ]
        block = build_snippet_block(snippets, artist='Joan Miró', specifics=[])
        assert 'contradict' in block.lower(), (
            "Verification constraint must mention self-contradictions"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Fridman is NOT described as Boston-based (acceptance criterion)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFridmanNotBostonBased:
    """Acceptance: Fridman named and NOT described as Boston-based without source."""

    def test_boston_based_fails_verification(self):
        """'Boston-based collector' fails because our only source says 'Russian collector'."""
        story = "Boris Fridman, a Boston-based collector, donated this portfolio to the MFA."
        result = verify_story_candidate(
            story_text=story,
            snippets=STOP1_SNIPPETS,
            credit_line=STOP1_CREDIT_LINE,
            stop_name="Stop 1",
        )
        # The location claim "Boston-based" should be unsourced
        loc_unsourced = [
            d for d in result['unsourced_details']
            if 'boston' in d['text'].lower()
        ]
        assert len(loc_unsourced) > 0 or not result['passed'], (
            "Should catch: 'Boston-based' is not in any snippet (source says 'Russian')"
        )

    def test_russian_collector_passes_verification(self):
        """'Russian collector' passes because artfocusnow.com says 'a Russian collector'."""
        story = "Boris Fridman, a Russian collector, donated several livres d'artiste to the MFA."
        result = verify_story_candidate(
            story_text=story,
            snippets=STOP1_SNIPPETS,
            credit_line=STOP1_CREDIT_LINE,
            stop_name="Stop 1",
        )
        # "Russian" should be sourced (artfocusnow snippet says "a Russian collector")
        loc_unsourced = [
            d for d in result['unsourced_details']
            if 'russian' in d['text'].lower()
        ]
        # Should not have 'Russian' as unsourced
        assert len(loc_unsourced) == 0, (
            f"'Russian collector' should be sourced. Unsourced: {result['unsourced_details']}"
        )
