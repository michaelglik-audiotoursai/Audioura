"""LOCAL-424: Tests that extract_claims actually extracts claims from real story text.

Red against `storied` (9acc72a): extract_claims returned 0 claims on the reference
story with six checkable assertions. LEAD measured this live (D369).

Green on this branch: the fixed extractor finds ≥6 claims, each with a subject.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from story_verifier import extract_claims


# The exact story text from LEAD's measurement (D369 / LOCAL-424 spec)
REFERENCE_STORY = (
    "Louis Broder, a visionary publisher known for his dedication to the livre "
    "d'artiste, commissioned Miro for this project. ... The lithographs were "
    "printed by the renowned Mourlot Freres ... Boris Fridman, a dedicated "
    "collector of artist books, generously donated this work to the Museum of "
    "Fine Arts, Boston. His gift enhances the museum's extensive collection of "
    "Surrealist-era printed works."
)


class TestExtractClaimsReturnsRealClaims:
    """extract_claims must return ≥6 claims on the reference story."""

    def test_minimum_claim_count(self):
        """The reference story has at least six checkable assertions."""
        claims = extract_claims(REFERENCE_STORY)
        assert len(claims) >= 6, (
            f"extract_claims returned {len(claims)} claims, expected ≥6. "
            f"Got: {[c.text for c in claims]}"
        )

    def test_every_claim_has_subject(self):
        """Every extracted claim must carry a subject (what it's about)."""
        claims = extract_claims(REFERENCE_STORY)
        for claim in claims:
            assert claim.subject, (
                f"Claim '{claim.text}' ({claim.claim_type}) has no subject — "
                f"verification cannot match it to a source without knowing "
                f"what entity the claim is about."
            )

    def test_person_descriptor_louis_broder(self):
        """'Louis Broder, a visionary publisher' must be extracted as a person_descriptor."""
        claims = extract_claims(REFERENCE_STORY)
        broder_claims = [c for c in claims if 'Louis Broder' in c.subject
                        and c.claim_type == 'person_descriptor']
        assert broder_claims, (
            f"No person_descriptor claim found for 'Louis Broder'. "
            f"Got types: {[(c.claim_type, c.subject) for c in claims]}"
        )
        # The descriptor must mention "publisher"
        assert any('publisher' in c.value for c in broder_claims), (
            f"Broder's descriptor must mention 'publisher'. "
            f"Got: {[c.value for c in broder_claims]}"
        )

    def test_attribution_commissioned(self):
        """'commissioned Miro' must be extracted as an attribution claim."""
        claims = extract_claims(REFERENCE_STORY)
        commission_claims = [c for c in claims if c.claim_type == 'attribution'
                           and 'Miro' in c.value]
        assert commission_claims, (
            f"No attribution claim for 'commissioned Miro'. "
            f"Got: {[(c.claim_type, c.text) for c in claims]}"
        )

    def test_attribution_mourlot(self):
        """'printed by the renowned Mourlot Freres' must be extracted."""
        claims = extract_claims(REFERENCE_STORY)
        mourlot_claims = [c for c in claims if c.claim_type == 'attribution'
                         and 'Mourlot' in c.subject]
        assert mourlot_claims, (
            f"No attribution claim for 'Mourlot Freres'. "
            f"Got: {[(c.claim_type, c.subject) for c in claims]}"
        )

    def test_person_descriptor_fridman(self):
        """'Boris Fridman, a dedicated collector' must be extracted."""
        claims = extract_claims(REFERENCE_STORY)
        fridman_claims = [c for c in claims if 'Fridman' in c.subject
                         and c.claim_type == 'person_descriptor']
        assert fridman_claims, (
            f"No person_descriptor claim for 'Boris Fridman'. "
            f"Got: {[(c.claim_type, c.subject) for c in claims]}"
        )
        assert any('collector' in c.value for c in fridman_claims), (
            f"Fridman's descriptor must mention 'collector'. "
            f"Got: {[c.value for c in fridman_claims]}"
        )

    def test_donation_museum_of_fine_arts(self):
        """'donated this work to the Museum of Fine Arts' must be extracted."""
        claims = extract_claims(REFERENCE_STORY)
        donation_claims = [c for c in claims if c.claim_type == 'donation']
        assert donation_claims, (
            f"No donation claim found. "
            f"Got types: {[(c.claim_type, c.text) for c in claims]}"
        )
        # Must mention Museum of Fine Arts
        assert any('Museum' in c.subject or 'Fine Arts' in c.subject
                  for c in donation_claims), (
            f"Donation claim must reference 'Museum of Fine Arts'. "
            f"Got: {[(c.subject, c.value) for c in donation_claims]}"
        )

    def test_institutional_claim(self):
        """'enhances the museum's extensive collection of Surrealist-era printed works'
        must be extracted as an institutional claim."""
        claims = extract_claims(REFERENCE_STORY)
        inst_claims = [c for c in claims if c.claim_type == 'institutional']
        assert inst_claims, (
            f"No institutional claim found. The most dangerous kind — "
            f"sounds like colour but is an assertion about a real museum's holdings. "
            f"Got types: {[(c.claim_type, c.text[:50]) for c in claims]}"
        )
        # Must mention Surrealist
        assert any('surrealist' in c.value.lower() for c in inst_claims), (
            f"Institutional claim must reference 'Surrealist-era'. "
            f"Got: {[c.value for c in inst_claims]}"
        )


class TestExtractClaimsDoesNotOverExtract:
    """Sanity: the extractor should not produce dozens of false claims."""

    def test_reasonable_count(self):
        """A 5-sentence story should produce 6-15 claims, not 50."""
        claims = extract_claims(REFERENCE_STORY)
        assert len(claims) <= 15, (
            f"Over-extraction: {len(claims)} claims from a 5-sentence story. "
            f"Expected 6-15. Got: {[c.text[:30] for c in claims]}"
        )

    def test_no_empty_claims(self):
        """No claim should have empty text or empty value."""
        claims = extract_claims(REFERENCE_STORY)
        for claim in claims:
            assert claim.text.strip(), f"Claim has empty text: {claim!r}"
            assert claim.value.strip(), f"Claim has empty value: {claim!r}"
