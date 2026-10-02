"""LOCAL-429: PARTS_OUT_OF_ORDER false positive — test the ordering fix.

The validator's ordering check must not flag Part 4 as out-of-order when
the only raw Part 4 sentence is primarily assigned to an earlier part.

Tests exercise the production symbol `validate_prolog_structure` directly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prolog_structure_validator import validate_prolog_structure


def _has_violation(violations, code):
    """Check if a specific violation code is present."""
    return any(v['code'] == code for v in violations)


class TestPartsOutOfOrderFalsePositive:
    """A sentence primarily serving Part 2 that incidentally names stops (raw P4)
    must not trigger PARTS_OUT_OF_ORDER."""

    def test_palais_artifact_no_false_positive(self):
        """The Palais Lascaris 141344 prolog does NOT trigger PARTS_OUT_OF_ORDER.

        Sentence 1 ('Within the museum, you will encounter four exquisite works:
        the Harpe by Naderman...') is primarily P2 (endpoints). It also names stops
        (raw P4), but that must not position Part 4 structurally before Part 3.
        """
        # Extracted from Palais_Lascaris__Nice__France_museum_tour_20260811_141344.txt
        prolog = (
            "You are about to explore the Palais Lascaris in Nice, home to a "
            "remarkable collection of historical musical instruments. Within the "
            "museum, you will encounter four exquisite works that showcase the "
            "evolution of musical craftsmanship across Europe: the Harpe by "
            "Naderman from Paris in 1780, the Sacqueboute ténor by Anton Schnitzer "
            "from Nuremberg in 1581, the Guitar by Antonio de Torres from Almeria "
            "in 1884, and the Basse de violon by Paolo Antonio Testore from Milan "
            "in 1696. The transformation of this venue into a music museum in 2011 "
            "allowed for the preservation and public display of these cultural "
            "treasures, each telling a unique story of their time and craftsmanship. "
            "At the upcoming stops, you will discover the French court's influence "
            "on musical instrument design with the Harpe by Naderman (Paris, 1780) "
            "and experience the global impact of Antonio de Torres's innovations."
        )
        meta = {
            'transport_mode': 'on_foot',
            'stop_names': [
                'Harpe by Naderman',
                'Sacqueboute ténor by Anton Schnitzer',
                'Guitar by Antonio de Torres',
                'Basse de violon by Paolo Antonio Testore',
            ],
        }
        violations = validate_prolog_structure(prolog, meta)
        assert not _has_violation(violations, 'PARTS_OUT_OF_ORDER'), (
            f"False positive: PARTS_OUT_OF_ORDER should not fire when "
            f"raw P4 sentence is primarily P2. Got: "
            f"{[v for v in violations if v['code'] == 'PARTS_OUT_OF_ORDER']}"
        )

    def test_genuine_out_of_order_still_detected(self):
        """A prolog where Part 4 genuinely has its own primary sentence before
        Part 3's primary sentence still triggers PARTS_OUT_OF_ORDER."""
        prolog = (
            "This is a walking tour. "
            "Walk 2 kilometers of flat terrain. "
            "At upcoming stops you will discover the opera house and the gallery. "
            "Built in 1871, it became famous for hosting international festivals."
        )
        meta = {
            'transport_mode': 'on_foot',
            'stop_names': ['opera house', 'gallery'],
        }
        violations = validate_prolog_structure(prolog, meta)
        assert _has_violation(violations, 'PARTS_OUT_OF_ORDER'), (
            f"Genuine out-of-order not detected! Part 4 (sentence 3) should "
            f"be flagged as appearing before Part 3 (sentence 4). "
            f"Violations: {violations}"
        )

    def test_correct_order_no_violation(self):
        """Parts in correct order (1→2→3→4) produce no ordering violation."""
        prolog = (
            "This is a walking tour of the historic quarter. "
            "Walk 2 kilometers of flat terrain along the promenade. "
            "Built in 1871, it became famous for hosting international festivals. "
            "At upcoming stops you will discover the opera house and the gallery."
        )
        meta = {
            'transport_mode': 'on_foot',
            'stop_names': ['opera house', 'gallery'],
        }
        violations = validate_prolog_structure(prolog, meta)
        assert not _has_violation(violations, 'PARTS_OUT_OF_ORDER'), (
            f"False positive on correctly-ordered prolog: {violations}"
        )


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
