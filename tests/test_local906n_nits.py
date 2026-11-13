"""LOCAL-906N -- 551 nits: mode-word capitalisation, one builder spelling, proper-name case. Offline, $0, generic fixtures."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_evidence_906h as de  # noqa: E402
import nits_906n as n  # noqa: E402
import refill_quality_906k as k  # noqa: E402
import route_content_896 as rc  # noqa: E402
import spoken_text_hygiene as sth  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906n"):
        rc.set_evidence_904({})
        de.clear()
        yield


def tour(bodies, titles, cat="walking"):
    out = f"<City> - {cat.title()} Tour\nTour-Category: {cat}\n\n"
    for i, (b, t) in enumerate(zip(bodies, titles), 1):
        out += (f"Stop {i}: {t}\n\nCoordinates: 10.{i}, 100.{i}\n\nType/Specialty: Landmark\n\n{b}\n\n"
                f"Directions: Continue to the next stop.\n\n")
    return out + f"That's {len(titles)} stops in all.\n"


@pytest.mark.parametrize("src,want", [
    ("As you walk around the market, you can see stalls.", "Around the market, you can see stalls."),
    ("As you walk here, you can see stalls.", "Here, you can see stalls."),
    ("While you stroll around here, you can see stalls.", "Here, you can see stalls."),
    ("As you walk here the market, you can see stalls.", "Around the market, you can see stalls."),
    ("Walk around the market to see stalls.", "Look around the market to see stalls."),
    ("Fruit grows on posts as you walk here. Then it ripens.", "Fruit grows on posts here. Then it ripens."),
    ("You can see stalls as you walk around the market, and sellers.", "You can see stalls around the market, and sellers."),
    ("Stalls line the road. As you walk around the market, you see fruit.", "Stalls line the road. Around the market, you see fruit."),
    ("You can walk around the fields, and rest.", "You can look around the fields, and rest."),
    ("Fruit hangs low as you walk here, and sellers call.", "Fruit hangs low here, and sellers call."),
])
def test_mode_fix(src, want):
    assert k._mode_fix(src) == want


def test_mode_fix_sentence_start_capitalised_in_tour():
    t = tour(["As you walk around the market, you can see stalls."], ["<Market>"], cat="driving")
    out = k.fix_mode_words(t, None)
    assert "Around the market, you can see stalls." in out and "here the market" not in out


def _two_stops(a, b):
    return tour([f"The statue was carved by {a} in 1958. Pilgrims climb up.",
                 f"The statue was carved by {b} in 1958. Visitors rest nearby."],
                ["Reclining Buddha Statue", "Buddha Statue Viewpoint"])


def test_builder_unified_to_evidence_spelling():
    t = _two_stops("Truong Dinh Tri", "Truong Dinh Y")
    ev = {"Reclining Buddha Statue": "The statue was carved by Truong Dinh Y in 1958.",
          "Buddha Statue Viewpoint": "A viewpoint near the statue."}
    logs = []
    out = n.unify_builder_names(t, ev, logs.append)
    assert "Truong Dinh Tri" not in out and out.count("Truong Dinh Y") == 2
    assert any("[LOCAL-906N] builder name unified: 'Truong Dinh Tri' -> 'Truong Dinh Y'" in m for m in logs)


def test_builder_article_wins_when_both_in_evidence():
    t = _two_stops("Truong Dinh Tri", "Truong Dinh Y")
    de.add({"Reclining Buddha Statue": [{"text": "A web page says Truong Dinh Y carved the statue.", "kind": "web", "url": "https://w.example.com/a"}],
            "Buddha Statue Viewpoint": [{"text": "The statue was carved by Truong Dinh Tri.", "kind": "article"}]}, "906n")
    ev = {"Reclining Buddha Statue": "A web page says Truong Dinh Y carved the statue.",
          "Buddha Statue Viewpoint": "The statue was carved by Truong Dinh Tri."}
    out = n.unify_builder_names(t, ev, None)
    assert "Truong Dinh Y" not in out and out.count("Truong Dinh Tri") == 2


def test_different_builders_not_merged():
    t = _two_stops("Truong Dinh Tri", "Pham Van Lam")
    ev = {"Reclining Buddha Statue": "Truong Dinh Tri carved it.", "Buddha Statue Viewpoint": "Pham Van Lam carved it."}
    assert n.unify_builder_names(t, ev, None) == t


def test_unrelated_objects_not_merged():
    t = tour(["The bridge was built by Truong Dinh Tri in 1900. Boats pass."],
             ["Old Bridge"]) 
    t2 = tour(["The temple was built by Truong Dinh Y in 1900. Monks pray."], ["Lotus Temple"])
    both = t.replace("That's 1 stops in all.\n", "") + t2.split("\n\n", 1)[1].replace("Stop 1", "Stop 2")
    assert n.unify_builder_names(both, {"Old Bridge": "Truong Dinh Tri", "Lotus Temple": "Truong Dinh Y"}, None) == both


def test_proper_case_restored():
    t = tour(["Ta Cu Mountain rises above the town. Pilgrims love it.",
              "The path to ta Cu Mountain is steep. The old town is near."], ["Ta Cu Mountain", "<Path>"])
    logs = []
    out = n.restore_proper_case(t, logs.append)
    assert "to Ta Cu Mountain is steep" in out and "ta Cu" not in out
    assert "The old town is near." in out and logs


def test_ordinary_lowercase_untouched():
    t = tour(["The Old Town is lovely. We walked through the old town at dusk."], ["<Town>"])
    assert n.restore_proper_case(t, None) == t


def test_folklore_disclosure_keeps_proper_name():
    out, ch = sth.disclose_or_drop_folklore("Ta Cu Mountain is said to grant wishes to pilgrims.")
    assert ch and "holds that Ta Cu Mountain" in out
    out2, _ = sth.disclose_or_drop_folklore("The statue is said to weep each spring.")
    assert "holds that the statue" in out2
