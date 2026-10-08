"""
LOCAL-618 #1: The Stop-1 orientation must not pre-tell the whole tour.

The Part-4 forward-connection builder concatenated per-stop facts into the
Stop-1 orientation, so the listener heard every stop's dated events and proper
nouns before reaching them. strip_later_stop_facts drops orientation sentences
that deliver a later-stop fact while preserving the connecting thread and the
"your first stop is X" pointer.

Pure/offline.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orientation_pretell import (
    extract_later_stop_terms,
    sentence_delivers_later_stop_fact,
    strip_later_stop_facts,
    build_forward_connection_prompt,
)

# A realistic Sevilla-shaped orientation that pre-tells Stops 2 and 3.
ORIENTATION = (
    "Orientation: You are at the Museo de Bellas Artes de Sevilla, a former convent "
    "that holds Spain's second-finest collection of Golden Age painting. "
    "In the stops ahead, you will encounter Murillo's Immaculate Conception painted "
    "in 1678 at The Virgin of the Napkin, and Zurbarán's 1631 Apotheosis of Saint "
    "Thomas Aquinas. Your first stop is The Virgin of the Napkin."
)
LATER_NAMES = ["Apotheosis of Saint Thomas Aquinas", "The Penitent Saint Jerome"]
LATER_TEXTS = [
    "Zurbarán completed the Apotheosis of Saint Thomas Aquinas in 1631 for the "
    "college of Santo Tomás. Thomas Aquinas sits enthroned above the four Doctors.",
    "The Penitent Saint Jerome shows the hermit in the wilderness, a work from 1650.",
]
STOP1_NAME = "The Virgin of the Napkin"
STOP1_TEXT = (
    "Murillo painted The Virgin of the Napkin in 1678. The Virgin holds the Christ "
    "child, said to be painted on a dinner napkin for the convent cook."
)


def test_strips_later_stop_fact_sentence():
    cleaned, dropped = strip_later_stop_facts(
        ORIENTATION, LATER_NAMES, LATER_TEXTS, STOP1_NAME, STOP1_TEXT)
    assert dropped >= 1, "the pre-tell sentence must be dropped"
    # The Zurbarán / Aquinas / 1631 later-stop fact must be gone.
    assert "Zurbarán" not in cleaned and "Aquinas" not in cleaned and "1631" not in cleaned, \
        f"later-stop fact survived: {cleaned}"


def test_preserves_where_you_are_and_pointer():
    cleaned, _ = strip_later_stop_facts(
        ORIENTATION, LATER_NAMES, LATER_TEXTS, STOP1_NAME, STOP1_TEXT)
    assert cleaned.lower().startswith("orientation:"), "label preserved"
    assert "Museo de Bellas Artes" in cleaned, "where-you-are sentence kept"
    assert "first stop is The Virgin of the Napkin" in cleaned, "pointer kept"


def test_keeps_stop1_own_fact():
    """A fact that belongs to Stop 1 (Murillo / 1678) must not be stripped even if
    it appears in the orientation, because it is not a later-stop fact."""
    orient = (
        "Orientation: You are at the museum. Murillo painted here in 1678. "
        "Your first stop is The Virgin of the Napkin."
    )
    cleaned, dropped = strip_later_stop_facts(
        orient, LATER_NAMES, LATER_TEXTS, STOP1_NAME, STOP1_TEXT)
    assert "Murillo" in cleaned, f"Stop-1 own fact wrongly stripped: {cleaned}"


def test_never_empties():
    """If every sentence is a later-stop fact, keep the first so there is an opening."""
    orient = (
        "Orientation: Zurbarán's 1631 Apotheosis of Saint Thomas Aquinas awaits. "
        "The Penitent Saint Jerome from 1650 awaits."
    )
    cleaned, _ = strip_later_stop_facts(
        orient, LATER_NAMES, LATER_TEXTS, STOP1_NAME, STOP1_TEXT)
    assert cleaned.strip(), "orientation must never be emptied"


def test_no_later_facts_is_a_noop():
    orient = (
        "Orientation: You are at the Museo de Bellas Artes de Sevilla, home to "
        "Golden Age painting. Your first stop is The Virgin of the Napkin."
    )
    cleaned, dropped = strip_later_stop_facts(
        orient, LATER_NAMES, LATER_TEXTS, STOP1_NAME, STOP1_TEXT)
    assert dropped == 0, f"nothing should be dropped, got {dropped}: {cleaned}"
    assert "Museo de Bellas Artes" in cleaned


def test_later_stop_name_itself_is_a_pretell():
    """Merely naming a later stop in Stop 1 counts as a pre-tell term."""
    terms = extract_later_stop_terms(["Apotheosis of Saint Thomas Aquinas"], [])
    assert "apotheosis" in terms["proper"] or "aquinas" in terms["proper"]


def test_forward_connection_prompt_bans_later_facts():
    p = build_forward_connection_prompt("The Virgin of the Napkin",
                                        "Sevillian Golden Age devotion", 3)
    low = p.lower()
    assert "first stop" in low
    assert "do not name" in low and "later stops" in low
    assert "The Virgin of the Napkin" in p


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
