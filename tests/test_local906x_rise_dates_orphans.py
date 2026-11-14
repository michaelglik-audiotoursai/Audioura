"""[LOCAL-906X] A length stated as a rise, an unsupported statue year, an orphan "his", neighbour / operator leftovers in the final
sweep, a forum comparison with the other objects named before the cue. $0, generic names (D769)."""
import inspect
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_evidence_906h as de  # noqa: E402
import drive_quality_906v as v  # noqa: E402
import leftovers_906f as f  # noqa: E402
import rise_dates_906x as x  # noqa: E402
import route_content_896 as rc  # noqa: E402
import stub_promo_906t as t  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906x"):
        rc.set_evidence_904({})
        de.clear()
        t.set_city_centers({})
        yield


def tour(stops):
    out = "Step-by-step audio guided tour of Alpha Peak is a driving tour.\n\n"
    for n, (title, body) in enumerate(stops, 1):
        out += f"Stop {n}: {title}\n\nCoordinates: 10.{n}, 100.{n}\n\nType/Specialty: Landmark\n\n{body}\n\nDirections: Go on.\n\n"
    return out


EV_MOUNT = "Alpha Peak is 649 meters above sea level. The cable car is 7,455 meters long and carries visitors to the summit."


def test_rise_above_elevation_dropped():
    log = []
    src = tour([("Alpha Peak", "Alpha Peak is a mountain of 649 meters. It has two shrines."),
                ("The cable car ascent", "A modern cable car awaits you. The ascent rises 1,279 meters from the base to the peak.")])
    out = x.run_pass(src, {"Alpha Peak": EV_MOUNT}, log.append)
    assert "1,279" not in out and "A modern cable car awaits you." in out
    assert any("exceeds the stated elevation" in m for m in log)


def test_true_rise_kept():
    src = tour([("Alpha Peak", "Alpha Peak rises 649 meters above sea level. It has two shrines.")])
    assert x.run_pass(src, {"Alpha Peak": EV_MOUNT}) == src


def test_length_stated_as_rise_rewritten_when_evidence_says_so():
    log = []
    src = tour([("Alpha Peak", "Alpha Peak is 649 meters high."),
                ("The cable car ascent", "The cable car runs to the top. The ascent rises 7,455 meters from the base to the peak.")])
    out = x.run_pass(src, {"Alpha Peak": EV_MOUNT}, log.append)
    assert "The line is about 7,455 meters long." in out and "rises 7,455" not in out
    assert any("rewritten" in m for m in log)


def test_length_stated_as_rise_dropped_without_line_evidence():
    ev = {"Alpha Peak": "Alpha Peak is 649 meters high. The path to the shrine is 300 meters in length."}
    src = tour([("Alpha Peak", "Alpha Peak is 649 meters high."), ("The path", "The walk is easy. The trail climbs 300 meters from the base.")])
    out = x.run_pass(src, ev)
    assert "climbs 300" not in out and "The walk is easy." in out


def test_a_covered_length_is_not_a_rise():
    src = tour([("Alpha Peak", "Alpha Peak is 649 meters high."), ("The cable car", "The cable car covers 7,455 meters in one ride.")])
    assert "covers 7,455" in x.run_pass(src, {"Alpha Peak": EV_MOUNT})


def test_no_elevation_known_keeps_the_claim():
    src = tour([("Beta Hill", "The path climbs 900 meters through the forest.")])
    assert x.run_pass(src, {}) == src


EV_STATUE = ("In 1958, a man named Truong Dinh Y began construction of the 49 meter-long Reclining Buddha statue. "
             "The pagoda was built in 1861.")


def test_unsupported_statue_year_dropped_and_logged():
    log = []
    src = tour([("Alpha Peak", "Alpha Peak is home to two pagodas. The pagoda was built in 1861, but the Buddha statue was added later in 1972."),
                ("The Reclining Buddha", "The Reclining Buddha statue was begun in 1958.")])
    out = x.run_pass(src, {"The Reclining Buddha": EV_STATUE, "Alpha Peak": "Alpha Peak is a peak."}, log.append)
    assert "1972" not in out and "begun in 1958" in out
    assert any("1972" in m and "1958" in m for m in log)


def test_supported_statue_year_kept():
    src = tour([("The Reclining Buddha", "The Reclining Buddha statue was begun in 1958.")])
    assert x.run_pass(src, {"The Reclining Buddha": EV_STATUE}) == src


def test_orphan_his_is_named():
    body = ("Near the summit stand two pagodas: the Upper Pagoda, Linh Son Truong Tho, and the Lower Pagoda, Long Doan. "
            "After his death in 1887, a group of his followers built the lower Long Doan Pagoda. "
            "In the 1870s, a Buddhist monk named Tran Huu Duc led a group of followers here. "
            "Tran Huu Duc spent much of his time meditating in a nearby cave.")
    out = f.repair_person_pronoun(tour([("Alpha Peak", body), ("Beta Hill", "A small hill with a view.")]), {})
    assert "After Tran Huu Duc's death in 1887" in out and "After his death" not in out


@pytest.mark.parametrize("s", [
    "Visitors often combine a trip here with a cable car ride up Alpha Peak, where an ancient pagoda sits among the clouds.",
    "You can also find local attractions and activities like sand dune jeep tours, cable car rides, and visits to fruit farms nearby.",
    "Sand dune jeep tours leave from the road.",
])
def test_final_sweep_drops_leftovers(s):
    src = tour([("Alpha Peak", "Alpha Peak is a mountain in a quiet province. " + s)])
    log = []
    out = v.final_sweep(src, log.append)
    assert s not in out and "Alpha Peak is a mountain" in out
    assert any("neighbour / operator leftover" in m for m in log)


def test_forum_comparison_before_the_cue_needs_evidence():
    s = "There are big Reclining Buddha statues in Thailand too, Wat Pho, Wat Lokayasutharam, but both are smaller than this one."
    assert t.comparative_unsupported(s, "The statue is 49 meters long.", [], "Reclining Buddha Statue") is not None
    ev = "The statue is larger than Wat Pho and Wat Lokayasutharam."
    assert t.comparative_unsupported(s, ev, [], "Reclining Buddha Statue") is None


def test_forum_comparison_dropped_in_the_pass():
    s = "There are big Reclining Buddha statues in Thailand too, Wat Pho, Wat Lokayasutharam, but both are smaller than this one."
    src = tour([("Reclining Buddha Statue", "This statue measures 49 meters in length. " + s)])
    out = t.run_pass(src, {"Reclining Buddha Statue": "The statue measures 49 meters."})
    assert "Wat Pho" not in out and "49 meters in length" in out


def test_last_word_still_ends_in_final_sweep():
    assert "return final_sweep(" in inspect.getsource(v.last_word)


def test_last_word_runs_the_rise_guard():
    src = tour([("Alpha Peak", "Alpha Peak is 649 meters high. It has two shrines."),
                ("The cable car ascent", "A modern cable car awaits you. The ascent rises 1,279 meters from the base to the peak.")])
    assert "1,279" not in v.last_word(src, {"Alpha Peak": EV_MOUNT})
