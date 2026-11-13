"""LOCAL-906G: cross-stop resolver needs object identity; reduplicated names stay; ship 'her'; Mayor role."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import leftovers_906f as f  # noqa: E402


def _two(t1, b1, t2, b2):
    return ("Alpha - Tour\nTour-Category: walking\n\n"
            f"Stop 1: {t1}\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: X\n\n{b1}\n\n"
            f"Stop 2: {t2}\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: X\n\n{b2}\n\nThat's 2 stops in all.\n")


def _same(t, ev):
    logs = []
    out = f.resolve_cross_stop(t, ev, logs.append)
    assert out == t, out
    assert "Sources differ" not in out and not logs


def test_probe1_two_churches():
    _same(_two("Alpha Church", "The church was built in 1850 by architect John Smith. It is calm.",
               "Beta Church", "The church was built in 1877 by Henry Richardson. It is calm here."),
          {"Alpha Church": "Built in 1850 by John Smith.", "Beta Church": "Henry Richardson designed it in 1877."})


def test_probe2_two_paintings():
    _same(_two("Water Lilies Room", "The painting was created by Claude Monet in 1872 at Argenteuil, near the river. Look.",
               "Boating Party Room", "The painting was created by Auguste Renoir in 1876 at Argenteuil, near the river. Look."),
          {"Water Lilies Room": "Claude Monet 1872 Argenteuil", "Boating Party Room": "Auguste Renoir 1876 Argenteuil"})


def test_two_museums_same_head():
    _same(_two("Louvre Museum", "The museum was founded in 1793 by decree. Look.",
               "Orsay Museum", "The museum was founded in 1986 by decree. Look."),
          {"Louvre Museum": "1793", "Orsay Museum": "1986"})


def test_two_statues_different_sculptors():
    _same(_two("Lion Statue", "The statue was carved by Anton Berg. Look.",
               "Eagle Statue", "The statue was carved by Carl Voss. Look."),
          {"Lion Statue": "Anton Berg", "Eagle Statue": "Carl Voss"})


def test_same_named_object_still_resolves_with_link_logged():
    t = _two("<Statue>", "The statue was constructed in 1963. Look.", "<Statue> hall", "The statue was constructed in 1958. Look.")
    logs = []
    out = f.resolve_cross_stop(t, {"<Statue>": "constructed in 1963.", "<Statue> hall": "constructed in 1958."}, logs.append)
    assert "Sources differ on the date: 1958 or 1963." in out
    assert any("linked by 'statue'" in x for x in logs), logs


def test_reduplicated_names_stay():
    for n in ("Walla Walla", "Bora Bora", "Pago Pago", "Sing Sing"):
        s = f"Visit {n} today."
        assert f._clean_names(s) == s


def test_mount_dups_still_fixed():
    assert f._clean_names("See Mount Mount today.") == "See Mount today."
    assert f._clean_names("See <Mountain> Mount today.") == "See <Mountain> today."
    assert f._clean_names("See Nui Ba Mount today.") == "See Nui Ba today."


def test_ship_her_kept():
    t = _two("Harbor", "After her launch in 1907, the ship served the harbor. Look.", "Pier", "A pier. Look.")
    assert "After her launch in 1907" in f.repair_person_pronoun(t, {}, None)


def test_mayor_offered_as_name():
    t = _two("Town Hall", "After his death the hall closed. Look.", "Pier", "A pier. Look.")
    out = f.repair_person_pronoun(t, {"Town Hall": "Mayor John Doe opened the hall."}, None)
    assert "John Doe" in out
