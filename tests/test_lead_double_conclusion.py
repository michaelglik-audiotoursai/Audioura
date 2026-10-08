"""LEAD 2026-10-08: thematic + legacy recap tail must be rebuilt to ONE thematic conclusion (Folkwang tour 468)."""
from tour_conclusion import has_thematic_conclusion, rebuild_conclusion

TXT = """Stop 1: Ecce homo
Daumier painted Ecce homo in 1850 and left it unfinished. The crowd presses toward the figure.

Stop 2: Das Fest des Bacchus (Abend)
Corot painted this evening scene in 1866. Bacchus presides over a gathering in waning light.

Together, these stops reveal the interplay between celebration and suffering in nineteenth-century painting.

From Ecce homo to Das Fest des Bacchus (Abend), you have followed the thread of the collection of Museum Folkwang.

That's 2 stops in all.

Along the way:
- Ecce homo: Daumier painted it in 1850.

If you would like to eat nearby we can build you a restaurant tour.
"""


def test_legacy_tail_is_not_preserved():
    assert has_thematic_conclusion(TXT) is False


def test_rebuild_leaves_one_thematic_conclusion():
    out = rebuild_conclusion(TXT, venue_name="Museum Folkwang")
    assert "you have followed the thread" not in out
    assert "Along the way" not in out
    assert out.count("restaurant tour") == 1
    assert out.rstrip().endswith("restaurant tour.")
    assert has_thematic_conclusion(out) is True
