"""[LOCAL-660] Boston walking v7 (tour 557 v7, Kiro 5/10) — four defects.

Each fixture is reduced from the real delivered tour
``~/Audioura/.continuous_dev/bench/W557v7/tour_557_v7.txt``:

  1. Stop 5 cut mid-sentence: "…here, the centuries gather and do not let"
  2. Garbled degrade: "The victims were Boston Massacre."  (+ the Massacre told
     twice in the same stop — D533/S27 must catch the second telling)
  3. Dangling pronoun: Stop 3 "His legacy is carved…" after the sentence that
     introduced George Francis Parkman was moved to Stop 1
  4. Directions: Stop 1→2 (stop 2 of 5) said "…marking the end of your walk
     exploring Massachusetts politics and current affairs" — only the leg into
     the LAST stop may say the walk is ending, and directions never echo theme.

Run:  python3 -m pytest tests/test_local660_walking_v7_defects.py -q
      python3 tests/test_local660_walking_v7_defects.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import work_first_evidence as wfe
import dangling_pronoun_gate as dpg
from unglossed_reference_gate import _degrade_sentence_is_wellformed
from derepetition_guard import check_cross_stop_fact_repetition, strip_repeated_facts
from directions_generator import (sanitize_directions_leg,
                                   sanitize_directions_in_text)


# ───────────────────────── Defect 1: mid-sentence truncation ────────────────

STOP5_CUT = """Tour-Category: walking

Stop 5: Old State House

Coordinates: 42.3605, -71.0572

The echoes of musket fire had barely faded when Lieutenant Governor Thomas Hutchinson appeared on the balcony. Below him, an armed and furious crowd pressed close. The grain of the brick, the echoes underfoot, the city's breath in the air—here, the centuries gather and do not let

Together, these stops reveal the enduring interplay between civic action and the physical spaces that have shaped Boston's political landscape. That's 5 stops in all."""


def test_defect1_midsentence_truncation_repaired():
    out, rep = wfe.repair_midsentence_truncation(STOP5_CUT)
    assert rep["repaired"] == 1
    assert "do not let" not in out
    # The stop now ends on the previous complete sentence.
    assert "an armed and furious crowd pressed close." in out
    # Conclusion survives untouched.
    assert "That's 5 stops in all." in out
    assert out.count("Stop 5:") == 1


def test_defect1_idempotent():
    once, _ = wfe.repair_midsentence_truncation(STOP5_CUT)
    twice, rep2 = wfe.repair_midsentence_truncation(once)
    assert rep2["repaired"] == 0
    assert once == twice


def test_defect1_complete_sentence_untouched():
    good = ("Tour-Category: walking\n\nStop 1: Foo\n\nThe dome gleams in the "
            "morning sun. It has stood for two centuries.\n\nDirections: Continue to Bar.")
    out, rep = wfe.repair_midsentence_truncation(good)
    assert rep["repaired"] == 0
    assert out == good


# ───────────────────────── Defect 2: garble + double-told ───────────────────

def test_defect2_copula_bare_entity_rejected_in_degrade():
    # In the degrade path (entity known) the garble is rejected…
    assert _degrade_sentence_is_wellformed(
        "The victims were Boston Massacre.", "Boston Massacre") is False
    assert _degrade_sentence_is_wellformed(
        "The event was the Boston Tea Party.", "Boston Tea Party") is False


def test_defect2_legit_predicate_nominatives_kept():
    # General validator (no entity) must keep well-formed predicate nominatives.
    for s in ("He was President of the United States.",
              "The result was chaos.",
              "The author was Shakespeare.",
              "The capital is Boston.",
              "Your first stop is Massachusetts State House."):
        assert _degrade_sentence_is_wellformed(s) is True, s


def test_defect2_double_told_massacre_within_stop():
    # The Massacre told twice in ONE stop — the second telling is flagged and
    # (when the stop is long enough) removed.
    filler = (" The building stands as a civic landmark observed by many "
              "visitors each year.") * 6
    tour = (
        "Stop 1: Alpha\n\nSomething unrelated happened in 1900 about Alpha and the city.\n\n"
        "Stop 2: Old State House\n\n"
        + filler.strip()
        + " On March 5, 1770, British soldiers fired into a crowd in what became "
          "the Boston Massacre. The balcony above saw Thomas Hutchinson address "
          "the mob below. On King Street on March 5, 1770, British soldiers fired "
          "into a hostile crowd, mortally wounding five colonists in the Boston "
          "Massacre." + filler
    )
    reps = check_cross_stop_fact_repetition(tour)
    within = [r for r in reps if r.get("within_stop")]
    assert within, "within-stop Massacre repeat not detected"
    out, actions = strip_repeated_facts(tour)
    assert any(a["removed"] and a.get("within_stop") for a in actions)
    assert out.count("Boston Massacre") == 1
    assert "King Street" not in out  # the inserted second telling was dropped


# ───────────────────────── Defect 3: dangling pronoun ───────────────────────

STOP3_DANGLING = """Tour-Category: walking

Stop 3: Parkman Bandstand

Coordinates: 42.3545, -71.0656

The Parkman Bandstand, built in 1912, is a circular, Greek Revival-style structure. Its columns and domed roof were designed to echo the equality of the public gatherings it hosts. His legacy is carved in the stone beneath your hand—a physical reminder that civic generosity can shape the city.

Directions: Continue to Faneuil Hall."""

STOP_WITH_ANTECEDENT = """Tour-Category: walking

Stop 5: Old State House

Lieutenant Governor Thomas Hutchinson appeared on the balcony above the crowd. His words did not erase the five deaths, but they held violence at bay that night.

Directions: Continue to the next stop."""


def test_defect3_dangling_his_dropped():
    out, n = dpg.strip_dangling_pronoun_openers_in_text(STOP3_DANGLING)
    assert n == 1
    assert "His legacy is carved" not in out
    # The real narration before it survives.
    assert "Greek Revival-style structure." in out
    assert out.count("Stop 3:") == 1


def test_defect3_resolved_pronoun_kept():
    # "His" resolves to Hutchinson named earlier in the same stop → KEEP.
    out, n = dpg.strip_dangling_pronoun_openers_in_text(STOP_WITH_ANTECEDENT)
    assert n == 0
    assert "His words did not erase" in out


def test_defect3_plural_pronoun_with_common_noun_kept():
    txt = ("Stop 1: Plaza\n\nAn armed crowd pressed close to the balcony. "
           "They refused to disperse until morning.\n\nDirections: Continue to Bar.")
    out, n = dpg.strip_dangling_pronoun_openers_in_text(txt)
    assert n == 0
    assert "They refused to disperse" in out


def test_defect3_idempotent():
    once, _ = dpg.strip_dangling_pronoun_openers_in_text(STOP3_DANGLING)
    twice, n2 = dpg.strip_dangling_pronoun_openers_in_text(once)
    assert n2 == 0 and once == twice


# ───────────────────────── Defect 4: directions end/theme ───────────────────

LEG_1_TO_2 = ("As you leave the Massachusetts State House, head south on Beacon "
              "Street. You'll soon arrive at Boston City Hall, a modern building "
              "with a distinctive clock tower, marking the end of your walk "
              "exploring Massachusetts politics and current affairs in Boston. "
              "It is roughly 400 meters away.")


def test_defect4_nonfinal_leg_end_language_stripped():
    out = sanitize_directions_leg(LEG_1_TO_2, is_last_leg=False,
                                  next_name="Boston City Hall")
    assert "end of your walk" not in out
    assert "exploring Massachusetts politics" not in out
    assert "Boston City Hall" in out
    assert "roughly 400 meters away" in out


def test_defect4_last_leg_may_say_final():
    leg = ("As you leave Faneuil Hall, walk down Congress Street. This is your "
           "final stop, the Old State House.")
    out = sanitize_directions_leg(leg, is_last_leg=True, next_name="Old State House")
    assert "final stop" in out


def test_defect4_navigation_through_not_stripped():
    leg = ("As you leave Boston City Hall, walk towards Tremont Street. Enjoy "
           "the walk through the park. It is roughly 850 meters away.")
    out = sanitize_directions_leg(leg, is_last_leg=False, next_name="Parkman Bandstand")
    assert out == leg  # legitimate spatial navigation, untouched


def test_defect4_text_level_only_last_leg_keeps_end():
    tour = (
        "Stop 1: A\n\nBody one.\n\nDirections: Head east, marking the end of your walk exploring politics. It is 400 meters away.\n\n"
        "Stop 2: B\n\nBody two.\n\nDirections: Head north to C. It is 300 meters away.\n\n"
        "Stop 3: C\n\nBody three. This is your final stop as the walk ends here.\n\n"
    )
    out, n = sanitize_directions_in_text(tour)
    assert n == 1  # only the Stop 1 leg (non-final) was edited
    assert "end of your walk" not in out
    assert "exploring politics" not in out
    # Stop 2's leg (also non-final) had no end/theme language → unchanged.
    assert "Head north to C" in out
    # idempotent
    out2, n2 = sanitize_directions_in_text(out)
    assert n2 == 0 and out2 == out


if __name__ == "__main__":  # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
