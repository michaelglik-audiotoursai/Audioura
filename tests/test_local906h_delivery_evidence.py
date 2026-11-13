"""LOCAL-906H -- delivery always has the evidence. Offline, $0, generic fixtures (D769), no network, no key."""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_bodies_905 as db905  # noqa: E402
import delivery_evidence_906h as de  # noqa: E402
import leftovers_906c as c906c  # noqa: E402
import route_content_896 as rc  # noqa: E402
import spoken_text_hygiene as sth  # noqa: E402

CLAIM = "It is the largest reclining Buddha in all of <Region>."
TOUR = (
    "<City> - Walking Tour\nTour-Category: walking\n\n"
    "Stop 1: <Cable Car> and the <Terminal>\n\nCoordinates: 10.1, 100.1\n\nType/Specialty: Transport\n\n"
    "You ride the <Cable Car> from the <Terminal> up the slope. It was opened in 1980 and carries visitors all day. "
    "The ride gives a wide view over the bay.\n\nDirections: Continue to the <Statue>. It is roughly 1 km away.\n\n"
    "Stop 2: <Statue>\n\nCoordinates: 10.2, 100.2\n\nType/Specialty: Monument\n\n"
    "The <Statue> sits on the ridge above the bay. " + CLAIM + " Pilgrims leave flowers at its feet every morning.\n\n"
    "You have now visited 2 stops in all. That's 2 stops in all.\n"
)
EV = {"<Statue>": "The <Statue> is one of the largest reclining Buddha statues in <Region>. Pilgrims leave flowers."}


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906h-a"):
        rc.set_evidence_904({})
        de.clear()
        yield


def _run(text, **kw):
    logs = []
    out = db905.ensure_bodies(text, log=logs.append, **kw)
    return out, logs


def test_no_evidence_arg_but_store_filled_drops_unsupported_superlative():
    de.add(EV, "889")                      # what the mocked 889 key-fact step does
    out, logs = _run(TOUR)                 # NO evidence argument
    assert "in all of <Region>" not in out
    assert any("[LOCAL-906C]" in m and "superlative scope unsupported" in m for m in logs), logs
    assert any("[LOCAL-906H] delivery evidence: 1/2 stops (889:1)" in m for m in logs), logs


def test_baseline_without_store_is_the_old_noop():
    de.clear()
    out, _logs = _run(TOUR)
    assert "in all of <Region>" in out     # 2-stop tour, no evidence anywhere: nothing to judge by


def test_empty_store_logs_no_evidence_line():
    _out, logs = _run(TOUR)
    assert any("[LOCAL-906C] final pass: evidence for 0/2 stops" in m and "NO evidence: scope/blocked/cross-stop checks skipped" in m
               for m in logs), logs


def test_summary_line_counts_stops_and_changes():
    de.add(EV, "889")
    _out, logs = _run(TOUR)
    line = [m for m in logs if "[LOCAL-906C] final pass:" in m]
    assert len(line) == 1 and "evidence for 1/2 stops" in line[0] and "NO evidence" not in line[0]
    assert re.search(r"\d+ change\(s\)", line[0])


def test_904_stash_fills_the_store():
    rc.set_evidence_904(EV)
    assert de.get() == EV
    out, _ = _run(TOUR)
    assert "in all of <Region>" not in out


def test_explicit_evidence_still_wins():
    de.add({"<Statue>": "The <Statue> is the largest reclining Buddha in all of <Region>."}, "889")
    out, _ = _run(TOUR, evidence_by_title=EV)
    assert "in all of <Region>" not in out


def test_store_is_job_scoped():
    de.add(EV, "889")
    with rc.job_scope("t906h-b"):
        assert de.get() == {}
        de.add({"<Other>": "x y z"}, "889")
        assert list(de.get()) == ["<Other>"]
    assert list(de.get()) == ["<Statue>"]


def test_report_is_logged_once_per_job():
    de.add(EV, "889")
    logs = []
    de.report(TOUR, logs.append)
    de.report(TOUR, logs.append)
    assert len([m for m in logs if "[LOCAL-906H] delivery evidence" in m]) == 1


def test_drop_unsupported_claims_uses_store():
    import route_leftovers_906 as l906
    de.add(EV, "889")
    out = l906.drop_unsupported_claims(TOUR, None, log=lambda m: None)
    assert "in all of <Region>" not in out


# ── item 3 ───────────────────────────────────────────────────────────────────────────────────────────────
S_DANGLE = "The statue is accessed by climbing an additional from the tram's upper station."


@pytest.mark.parametrize("q", ["an additional", "a further", "an extra"])
def test_dangling_quantifier_removed(q):
    out = de.drop_dangling_quantifier(S_DANGLE.replace("an additional", q))
    assert q not in out and "climbing from the tram's upper station." in out


def test_dangling_quantifier_at_clause_end_drops_sentence():
    t = "The path is steep. The statue is reached by climbing an additional.\nNext line."
    out = de.drop_dangling_quantifier(t)
    assert "additional" not in out and "The path is steep." in out


def test_weak_quantifier_only_in_measure_sentence():
    assert de.drop_dangling_quantifier("Climb another from the gate to reach the top.") == \
        "Climb from the gate to reach the top."
    keep = "Another from the same family opened a shop here."
    assert de.drop_dangling_quantifier(keep) == keep
    keep2 = "Some of the carvings are original. Another to see is the gate."
    assert de.drop_dangling_quantifier(keep2) == keep2


def test_legit_quantifier_with_number_untouched():
    t = "The statue is accessed by climbing an additional 120 steps from the tram's upper station."
    assert de.drop_dangling_quantifier(t) == t


def test_source_cut_removes_whole_measure_phrase():
    text = ("Stop 1: <Statue>\n\nThe statue is accessed by climbing an additional 120 steps from the tram's upper "
            "station. It looks over the bay.\n")
    out, _rep = sth.audit_seating_capacity(text, "", {"<Statue>": "A statue above the bay."})
    assert "additional" not in out and "120" not in out
    assert "climbing from the tram's upper station" in out


def test_final_pass_removes_dangling_quantifier():
    t = TOUR.replace("It was opened in 1980", "It is reached after climbing an additional from the station and opened in 1980")
    de.add(EV, "889")
    out, _ = _run(t)
    assert "an additional" not in out


# ── item 4 ───────────────────────────────────────────────────────────────────────────────────────────────
def test_one_count_sentence():
    out, _ = _run(TOUR)
    assert len(re.findall(r"(?i)\b\d+ stops\b", out.split("Stop 2:")[1])) == 1
    assert "That's 2 stops in all." in out and "visited" not in out


def test_count_sentence_not_touched_when_only_one():
    t = TOUR.replace("You have now visited 2 stops in all. ", "")
    assert de.dedupe_count_sentences(t) == t
    t2 = TOUR.replace("That's 2 stops in all.", "")
    assert de.dedupe_count_sentences(t2) == t2


def test_count_dedupe_after_stop_removed_keeps_delivered_count():
    out = db905.fix_counts(TOUR.replace("That's 2 stops in all.", "That's 3 stops in all."), None)
    assert out.count("stops in all") == 1 and "That's 2 stops in all" in out
