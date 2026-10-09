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
