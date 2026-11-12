"""LOCAL-904 -- single-place polish: a floor under the caps (evidence -> neighbour -> honest), the address rule
for a district token without an admin prefix, and the off-site suggestion filler. Generic fixtures, offline, $0."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pin_snap  # noqa: E402
import route_content_896 as rc  # noqa: E402
import strict_grounding_gate as sgg  # noqa: E402

REV = "Lập Nghĩa, Xã Hàm Thuận Nam, Tỉnh Lâm Đồng, Việt Nam"
ADDR = "Thuan Hoa, Ham Thuan Nam, Kappa, Zedland"
MOOD2 = ("The posture and serene countenance are deliberate, symbolizing peace and harmony.",
         "As you take in the statue's tranquil expression, you feel the calm and peace of the whole mountainside.")
EVIDENCE = {"Beta Statue": ("The Beta Statue is 49 meters long and 7 meters high. "
                            "Visitors reach the Beta Statue by cable car or by a hike through the forest. "
                            "The Omega Pagoda beside the Beta Statue was built in 1861. "
                            "Ticket offers and skip-the-line promos are sold online.")}


def _fx():
    with open(os.path.join(ROOT, "tests", "fixtures", "local904_single_place_generic.txt"), encoding="utf-8") as f:
        return f.read()


def _stop_body(text, n):
    for s, e, num, _t in rc._stop_blocks(text):
        if num == n:
            return rc._content_sentences_of(text[s:e].split("\n"), n == len(rc._stop_blocks(text)))
    raise AssertionError(n)


# ── address rule ────────────────────────────────────────────────────────────
def test_address_part_without_admin_prefix_matches_stripped_reverse_part():
    assert pin_snap.address_agrees(ADDR, REV, "")
    assert pin_snap.address_agrees("Ta Cu Mountain, " + ADDR, REV, "")
    assert pin_snap.address_agrees("Thuan Hoa, Xã Hàm Thuận Nam, Kappa, Zedland", REV, "")   # with a prefix too


def test_wrong_district_or_province_only_match_is_still_dropped():
    assert not pin_snap.address_agrees("Thuan Hoa, Phan Thiet, Kappa, Zedland", REV, "")
    assert not pin_snap.address_agrees("Foo, Phan Thiet, Viet Nam", REV, "")       # province / country never count


def test_both_stops_decided_by_one_rule():
    pois = [{"name": "Alpha Mountain", "address": ADDR}, {"name": "Beta Statue", "address": "Alpha Mountain, " + ADDR}]
    rows = [{"snapped": True, "new_coordinate": (10.8, 107.8)}] * 2
    logs = []
    dropped = pin_snap.verify_addresses(pois, rows, reverse_fn=lambda a, b: REV, log=logs.append)
    assert dropped == 0 and all(p["address"] for p in pois), logs


# ── off-site suggestion ─────────────────────────────────────────────────────
def test_offsite_suggestion_dropped_only_without_support():
    s = "As you explore, you might also visit a local dragon fruit farm on your way back."
    assert rc.is_offsite_suggestion(s, {"mountain", "statue"})
    assert not rc.is_offsite_suggestion(s, {"dragon", "fruit", "farm"})                 # the evidence holds it
    assert not rc.is_offsite_suggestion("You can reach the statue by hiking or a cable car.", set())
    assert not rc.is_offsite_suggestion("You might also visit the 1861 pagoda nearby.", set())


# ── floor: evidence -> neighbour -> honest ──────────────────────────────────
def test_replay_with_evidence_refills_from_evidence_no_mood():
    logs = []
    out = rc.apply_single_place_guards(_fx(), logs.append, evidence_by_title=EVIDENCE)
    body = _stop_body(out, 2)
    assert len(body) >= 3
    assert not any(rc.mood_terms(x) for x in body), body
    for m in MOOD2:
        assert m not in out
    assert "dragon fruit" not in out
    assert any("[LOCAL-904] Stop 2 thin (1 sentence) -> refilled from evidence" in x for x in logs), logs
    assert "Address: Alpha Mountain, Thuan Hoa" in out
    assert len(set(map(rc.fold, body))) == len(body)
    assert rc.apply_single_place_guards(out, evidence_by_title=EVIDENCE) == out, "idempotent"


def test_replay_without_evidence_uses_neighbour_then_honest():
    logs = []
    out = rc.apply_single_place_guards(_fx(), logs.append)
    body = _stop_body(out, 2)
    assert len(body) >= 3
    assert not any(rc.mood_terms(x) for x in body if sgg.NO_HISTORY_DISCLOSURE not in x), body
    assert any("Stop 2 thin (1 sentence) -> refilled from honest" in x for x in logs), logs
    assert any(sgg.NO_HISTORY_DISCLOSURE in x for x in body)
    for m in MOOD2:
        assert m not in out
    assert "dragon fruit" not in out
    # exactly one neighbour sentence (about the statue), taken from Stop 1's body
    s1 = set(rc.fold(x) for x in _stop_body(out, 1))
    assert sum(rc.fold(x) in s1 for x in body) == 1
    assert rc.apply_single_place_guards(out) == out, "idempotent"


def test_neighbour_stage_when_it_is_enough():
    t = _fx().replace(MOOD2[0], "").replace(MOOD2[1], "")
    t = t.replace("stretching an impressive 49 meters in length.",
                  "stretching an impressive 49 meters in length. The sculptors finished the face last.")
    before = t.replace("The sculptors finished the face last.",
                       "The sculptors finished the face last. " + " ".join(MOOD2))
    logs = []
    out = rc.refill_thin_stops(before, t, None, logs.append)
    assert len(_stop_body(out, 2)) == 3, out
    assert any("Stop 2 thin (2 sentences) -> refilled from neighbour" in x for x in logs), logs


def test_a_dropped_sentence_is_never_readded():
    before = _fx()
    after = rc.cap_single_place_filler(before)
    out = rc.refill_thin_stops(before, after, {"Beta Statue": " ".join(MOOD2) + " " + EVIDENCE["Beta Statue"]})
    for m in MOOD2:
        assert m not in out


def test_stop_not_thinned_by_caps_is_left_alone():
    t = _fx()
    assert rc.refill_thin_stops(t, t) == t
