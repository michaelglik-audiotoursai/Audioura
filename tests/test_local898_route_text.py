"""LOCAL-898 -- route-tour text leftovers: N-minute / number-word times, turn-by-turn Directions, conflicting
creators, short hops, distinct Type/Specialty, body before Directions. Generic fixtures, offline, $0."""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import route_content_896 as rc  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
INFO = {"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Mountain",
        "through": ["Sigma Town"], "region": "Delta province", "origin_locality": "Alpha Quarter, Beta Bay"}


@pytest.fixture(autouse=True)
def _route():
    rc.set_route(INFO)
    rc._POINTS.clear()
    yield
    rc.clear_route()
    rc._POINTS.clear()


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _blocks(text):
    return {n: text[s:e] for s, e, n, _t in rc._stop_blocks(text)}


def _dirs(block):
    m = re.search(r"(?m)^Directions:\s*(.*)$", block)
    return m.group(1) if m else None


def _body(block):
    return " ".join(ln for i, ln in enumerate(block.split("\n"))
                    if i and ln.strip() and not rc._KEYED.match(ln) and not rc._CLOSING_LINE.match(ln.strip()))


# ── 1 / 2: times ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("s", ["a 40-minute trip", "a 2-hour drive", "about two minutes", "roughly five hours",
                               "a few minutes", "several hours", "half an hour", "15 minutes", "an hour"])
def test_time_forms_are_recognised(s):
    assert rc._MINUTES.search(s) and rc._has_travel(f"You arrive after {s} from there.")


def test_body_hyphenated_time_sentence_is_dropped():
    t = ("Stop 1: Start\nCoordinates: 1.0, 1.0\nBody one is fine here for sure.\n\n"
         "Stop 2: Gamma Mountain\nCoordinates: 1.1, 1.1\nYou reach Gamma Mountain after about a 40-minute trip to Delta. "
         "The mountain has two halls and a long stair to the top.\n")
    out = rc.strip_body_travel(t)
    assert "minute" not in out and "two halls" in out


# ── 3 / 5 / 6c / 6d / 6e: Directions ────────────────────────────────────────
def _two(dline, a="1.00, 1.00", b="1.10, 1.10"):
    return (f"Stop 1: First Hall\nCoordinates: {a}\nA body sentence about the first hall here.\n"
            f"Directions: {dline}\n\nStop 2: Second Hall\nCoordinates: {b}\nA body about the second hall.\n")


@pytest.mark.parametrize("line", [
    "Continue southeast on National Route 1A from Beta, then take a right onto the road leading to Delta. "
    "You'll notice the vibrant dragon fruit fields lining the route.",
    "Drive east for about two minutes, and you'll reach Second Hall. Enjoy the drive!",
    "From the plantations, head west on National Route 1A, then turn onto Gamma Mountain Road. "
    "The road winds up the mountain, revealing lush greenery and stunning vistas."])
def test_directions_hold_only_continue_distance_scenery(line):
    d = _dirs(rc.normalize_directions(_two(line)))
    assert d.startswith("Continue to Second Hall.") and re.search(r"It is roughly \d+\.\d km away\.", d)
    assert not re.search(r"(?i)\b(turn|take|right|left|exit|onto|head|drive|minute|road|street|east|west|north|south)\b|route\s*\d", d.replace("Continue to", ""))
    assert len(rc.split_sentences(d)) <= 3


def test_scenery_clause_is_kept_once_and_clean():
    d = _dirs(rc.normalize_directions(_two("Head west on Route 9. You'll notice the lush rice fields lining the route. "
                                           "You'll see the sea glitter far off.")))
    assert d.count("You'll") == 1 and "rice fields" in d


def test_going_back_or_descending_is_not_narrated():
    d = _dirs(rc.normalize_directions(_two("After enjoying the views, retrace your route back down the mountain via "
                                           "the cable car. The descent offers a beautiful perspective of the landscape below.")))
    assert d.startswith("Continue to Second Hall.") and not re.search(r"(?i)retrace|descent|back|cable", d)


def test_no_distance_when_an_end_is_unpinned():
    t = _two("Head south for 3 km.").replace("Coordinates: 1.10, 1.10\n", "")
    assert _dirs(rc.normalize_directions(t)) == "Continue to Second Hall."


# ── 5 / 6e: short hops and shared pins ──────────────────────────────────────
def test_under_one_km_is_walk_on_without_distance():
    d = _dirs(rc.normalize_directions(_two("Drive northeast for about 500 meters, and you'll reach Second Hall.",
                                           "1.0000, 1.0000", "1.0040, 1.0000")))
    assert d == "Walk on to Second Hall."


def test_shared_pin_is_walk_on():
    d = _dirs(rc.normalize_directions(_two("Enjoy the drive!", "1.0, 1.0", "1.0, 1.0")))
    assert d == "Walk on to Second Hall."


# ── 4: creators ─────────────────────────────────────────────────────────────
CRE = ("Stop 1: Epsilon Hall\nCoordinates: 1.0, 1.0\nThe hall is famous for its stone statue of the Reclining Giant, "
       "which is long and was built in 1963 by sculptor Theta One. Pilgrims visit it daily.\n"
       "Directions: Continue to The Reclining Giant.\n\n"
       "Stop 2: The Reclining Giant\nCoordinates: 1.0, 1.0\nThe statue was carved by Theta Two and is a main attraction. "
       "It is open all year.\n")


def test_neither_creator_in_evidence_drops_both():
    out = rc.consistent_creators(CRE, {"Epsilon Hall": "A hall.", "The Reclining Giant": "A statue."})
    assert "Theta" not in out and "Pilgrims visit" in out and "open all year" in out


def test_evidence_supported_creator_is_kept():
    out = rc.consistent_creators(CRE, {"The Reclining Giant": "The statue was carved by Theta Two in the 1960s."})
    assert "Theta Two" in out and "Theta One" not in out


def test_both_supported_or_same_person_is_untouched():
    ev = {"The Reclining Giant": "Built by Theta One. Carved by Theta Two."}
    assert rc.consistent_creators(CRE, ev) == CRE
    same = CRE.replace("Theta Two", "Theta One Senior")
    assert rc.consistent_creators(same, {"x": "y"}) == same


def test_unrelated_objects_with_different_makers_are_untouched():
    t = ("Stop 1: Old Bridge\nCoordinates: 1.0, 1.0\nThe bridge was built by Mara Vel in 1900.\n\n"
         "Stop 2: Lantern Garden\nCoordinates: 1.1, 1.1\nThe pavilion was built by Orin Tash in 1950.\n")
    assert rc.consistent_creators(t, {"x": "y"}) == t


def test_no_evidence_map_leaves_creators():
    assert rc.consistent_creators(CRE, None) == CRE and rc.consistent_creators(CRE, {}) == CRE


# ── 6a: Type/Specialty ──────────────────────────────────────────────────────
def test_type_specialty_not_copied_from_previous_stop():
    t = ("Stop 1: Sigma Town and River\nCoordinates: 1.0, 1.0\nType/Specialty: City and river\nBody one.\n\n"
         "Stop 2: Dragon fruit country – the plantations\nCoordinates: 1.1, 1.1\nType/Specialty: City and river\nBody two.\n\n"
         "Stop 3: A Quiet Corner\nCoordinates: 1.2, 1.2\nType/Specialty: City and river\nBody three.\n")
    b = _blocks(rc.distinct_type_specialty(t))
    assert "Type/Specialty: Agricultural area" in b[2]
    assert "Type/Specialty" not in b[3] and "City and river" in b[1]


# ── 6b: body before Directions ──────────────────────────────────────────────
def test_directions_moved_below_body():
    t = ("Stop 1: Cable Hall\nCoordinates: 1.0, 1.0\nType/Specialty: Cable car ride\n"
         "Directions: Enjoy the drive! Continue to Next Hall.\nA body sentence that was added after.\n\n"
         "Stop 2: Next Hall\nCoordinates: 1.1, 1.1\nBody two.\n")
    b = _blocks(rc.order_directions_last(t))[1]
    assert b.index("A body sentence") < b.index("Directions:")


def test_sgg_empty_body_goes_before_directions():
    import strict_grounding_gate as sgg
    t = ("Stop 1: Cable Hall\nCoordinates: 1.0, 1.0\nType/Specialty: Cable car ride\n"
         "Directions: Continue to Next Hall.\n\nStop 2: Next Hall\nCoordinates: 1.1, 1.1\nBody two.\n")
    out = sgg._replace_block_body(t, 1, ["An honest body sentence."])
    b = _blocks(out)[1]
    assert b.index("An honest body") < b.index("Directions:")


def test_last_stop_closing_stays_last():
    t = ("Stop 1: A Hall\nCoordinates: 1.0, 1.0\nBody.\n\nStop 2: B Hall\nCoordinates: 1.1, 1.1\n"
         "Directions: Look around.\nA late body sentence here.\n"
         "From Alpha Lodge to Gamma Mountain, this route is the one you chose — your own path, in your own order.\n")
    out = rc.order_directions_last(t)
    assert out.index("late body") < out.index("Directions:") < out.index("this route is the one")


# ── replays ─────────────────────────────────────────────────────────────────
def _replay(name, ev=None):
    t = _fx(name)
    pts = {"alpha lodge": (10.98, 108.25), "sigma town": (10.92, 108.10), "gamma mountain": (10.76, 107.89)}
    for k, v in pts.items():
        rc._POINTS[k] = v
    t = rc.strip_body_travel(rc.simplify_directions(t))
    return rc.finalize_898(t, ev)


def _assert_clean(out):
    blocks = _blocks(out)
    pins = {n: rc._pin(b) for n, b in blocks.items()}
    for n, b in blocks.items():
        assert not re.search(r"(?i)\b(minutes?|hours?)\b", _body(b)), (n, _body(b))
        d = _dirs(b)
        if d:
            full, d = d, re.sub(r"^(?:Continue|Walk on) to .*?\.(?= |$)", "", d)   # the next stop's title is not an instruction
            assert not re.search(r"(?i)\b(turn|right|left|exit|onto|head|take|retrace|descen\w+|minutes?)\b|"
                                 r"\bRoute\s*\d|\b\d+[A-Z]\b|\b(street|road)\b", d), (n, d)
            assert not (re.search(r"(?i)\bfor (about|roughly)\b", d) and re.search(r"km away", d))
            if n + 1 in blocks and pins[n] and pins[n + 1] and rc._km(pins[n], pins[n + 1]) < 1.0:
                assert not re.search(r"(?i)\bdrive\b", full.split(".")[0].split(" to ", 1)[0]) and full.startswith("Walk on to"), (n, full)
        assert b.count("Directions:") <= 1


def test_replay_lead_proof_tour():
    out = _replay("local898_tour.txt", {"The Reclining Buddha": "A reclining statue on the mountain, open all year."})
    _assert_clean(out)
    assert len(re.findall(r"Theta (?:One|Two)", out)) == 0          # no evidence names either -> both dropped
    b = _blocks(out)
    assert "Continue to Sigma Town" not in _dirs(b[2]) and _dirs(b[2]).startswith("Continue to")
    assert _dirs(b[5]).startswith("Walk on to") and _dirs(b[4]).startswith("Walk on to")
    assert _dirs(b[7]).startswith("Walk on to")


def test_replay_lead_proof_one_creator_kept_with_evidence():
    out = _replay("local898_tour.txt", {"The Reclining Buddha": "The statue was carved by Theta Two in 1963."})
    assert "Theta Two" in out and "Theta One" not in out


def test_replay_cloud_tour():
    out = _replay("local898_cloud_tour.txt")
    _assert_clean(out)
    b = _blocks(out)
    assert "Type/Specialty: City and river" not in b[3]
    five = b[5]
    assert five.index("We could not confirm") < five.index("Directions:")      # body before Directions [LOCAL-900: kind-aware sentence]
    assert not re.search(r"(?i)retrace|descent|back down", out)
    assert all(_dirs(b[n]).startswith("Walk on to") for n in (4, 5, 6, 7))   # one shared pin
