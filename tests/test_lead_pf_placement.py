"""LEAD 2026-10-08 (D640 note 1): practical facts form ONE opening paragraph, independent of labels."""
from practical_facts_gate import place_practical_facts_in_opening

T = """Step-by-Step Audio Guided Tour: Frick Collection - Museum Tour

Stop 1: Portrait of Sir Thomas More

Coordinates: 40.77, -73.96

Stand slightly left of the portrait. More clutches a book. The museum is open daily except Tuesday. Admission is 30 dollars for adults.

Holbein painted More in 1527.

Stop 2: Officer and Laughing Girl

Vermeer painted it around 1657.
"""


def test_facts_become_first_paragraph_of_stop1():
    out, n = place_practical_facts_in_opening(T)
    assert n == 2
    s1 = out.split("Stop 1:")[1]
    paras = [p for p in s1.split("\n\n") if p.strip() and not p.strip().startswith(("Portrait", "Coordinates"))]
    assert paras[0].startswith("The museum is open daily except Tuesday.")
    assert out.count("The museum is open") == 1
    assert "More clutches a book." in out


def test_idempotent():
    out, _ = place_practical_facts_in_opening(T)
    assert place_practical_facts_in_opening(out)[1] == 0


def test_single_newline_blocks_never_flattened_R9():
    """NG 495 (R9): a Stop block joined by single newlines was flattened into one line."""
    t = ("T\n\nStop 1: A\n\nThe X is an art museum in London.\n\nOrientation: Stand. The museum is open daily from 10:00 to 6:00.\n\n"
         "Directions: Your final stop: B.\nStop 2: B\nAddress: Trafalgar Square\nCoordinates: 51.5, -0.12\nOrientation: Stand back. Admission is free.\nNarr.\n")
    out, _ = place_practical_facts_in_opening(t)
    assert "\nStop 2: B\nAddress: Trafalgar Square\nCoordinates: 51.5, -0.12\n" in out
    assert out.count("Your final stop") == 1


def test_bequest_amount_is_not_an_admission_fact():
    # LEAD 2026-10-09: tour 557 v7 moved Stop 3's Parkman bequest into the Stop-1 opening.
    import practical_facts_gate as g
    assert not g._is_practical_facts_sentence(
        "The bandstand honors George Francis Parkman, who left a $5 million bequest for Boston Common.")
    assert not g._is_practical_facts_sentence("He sold it for $500.")
    assert g._is_practical_facts_sentence("Tickets are $25 for adults.")


def test_open_to_debate_and_decimal_millions_are_not_practical_facts():
    # LEAD 2026-10-09: 557 v8 moved "cost $26.5 million by 1969" and "is open to debate" into the Stop-1 opening.
    import practical_facts_gate as g
    assert not g._is_practical_facts_sentence("Their design cost $26.5 million by 1969.")
    assert not g._is_practical_facts_sentence("The truth of that binding is open to debate.")
    assert g._is_practical_facts_sentence("The museum is open daily from 10 AM.")
    assert g._is_practical_facts_sentence("Admission is $12.50 for adults.")
