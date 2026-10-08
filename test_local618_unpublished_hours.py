"""
LOCAL-618 #4: Spoken hours missing when the preflight returns none.

When the venue's own pages / preflight yield NO hours, the Stop-1 opening section
must say ONCE "Opening hours weren't published where we could read them" and must
NEVER tell the listener to "check <domain>". The say-once guard
(practical_facts_gate.collapse_website_pointers) collapses duplicates tour-wide.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import about_museum_stop as am
from practical_facts_gate import collapse_website_pointers, is_website_pointer_sentence

HONEST = "Opening hours weren't published where we could read them."


def test_fallback_is_the_honest_sentence():
    s = am._visiting_fallback_sentence("museefabre.fr")
    assert s == HONEST, f"unexpected fallback: {s!r}"


def test_fallback_never_says_check_domain():
    s = am._visiting_fallback_sentence("museefabre.fr")
    low = s.lower()
    assert "check" not in low
    assert "before you go" not in low
    assert "museefabre.fr" not in low
    assert "website" not in low


def test_opening_section_uses_honest_line_when_no_facts():
    class _About:
        narration = "The museum was founded in 1825."
        practical_facts = ""          # preflight / own pages returned none
        site_domain = "museefabre.fr"
        as_of = "October 2026"
        museum_name = "Mus\u00e9e Fabre"
        sources = []
    section = am.build_opening_section(_About())
    assert HONEST in section, f"honest line missing: {section!r}"
    assert "museefabre.fr" not in section
    assert "before you go" not in section.lower()


def test_say_once_collapses_duplicates():
    text = (
        "Welcome to the museum. " + HONEST + "\n\n"
        "Here is the first work. " + HONEST + "\n\n"
        "And the second. " + HONEST
    )
    cleaned, removed = collapse_website_pointers(text)
    assert removed == 2, f"expected 2 removed, got {removed}"
    assert cleaned.count(HONEST) == 1, "exactly one honest line must remain"


def test_honest_line_recognised_as_pointer():
    assert is_website_pointer_sentence(HONEST)


def test_every_path_inserts_honest_line_when_no_hours():
    """A delivered tour that speaks no hours gets the honest line once, after the
    Stop-1 orientation."""
    from practical_facts_gate import ensure_unpublished_hours_line, tour_speaks_hours
    text = (
        "Stop 1: The Virgin of the Napkin\n\n"
        "Orientation: You are at the Museo de Bellas Artes de Sevilla.\n\n"
        "Murillo painted this Virgin in 1678.\n\n"
        "Stop 2: Another work\n\nIt hangs nearby."
    )
    assert not tour_speaks_hours(text)
    out, inserted = ensure_unpublished_hours_line(text)
    assert inserted is True
    assert out.count(HONEST) == 1
    # Placed in the orientation paragraph, up front.
    _orient_para = [p for p in out.split("\n\n") if "Orientation:" in p][0]
    assert HONEST in _orient_para


def test_every_path_noop_when_hours_spoken():
    from practical_facts_gate import ensure_unpublished_hours_line
    text = ("Orientation: You are at the museum.\n\n"
            "The museum is open Tuesday to Sunday, 10:00 AM to 6:00 PM.")
    out, inserted = ensure_unpublished_hours_line(text)
    assert inserted is False
    assert HONEST not in out


def test_every_path_noop_when_line_already_present():
    from practical_facts_gate import ensure_unpublished_hours_line
    text = "Orientation: You are at the museum. " + HONEST
    out, inserted = ensure_unpublished_hours_line(text)
    assert inserted is False
    assert out.count(HONEST) == 1


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  [PASS] {fn.__name__}"); passed += 1
        except Exception:
            print(f"  [FAIL] {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
