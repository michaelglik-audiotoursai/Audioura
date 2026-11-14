"""[LOCAL-906T] Stub tail, PERSON-CAP place words, ticket / guide / "from all over the world" promo, unhedged records and comparatives,
the closing variant, a neighbour's fact, a bearing that contradicts the pin, a coarse pin. $0, generic names (D769)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_evidence_906h as de  # noqa: E402
import derepetition_guard as dg  # noqa: E402
import language_dest_906s as s906s  # noqa: E402
import route_content_896 as rc  # noqa: E402
import stub_promo_906t as t  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906t"):
        rc.set_evidence_904({})
        de.clear()
        t.set_city_centers({})
        yield


K1 = "The old tower rises above the river and the market square."
K2 = "A small shrine sits near the summit path."
K3 = "Pilgrims climb a stone stair to the summit each spring."


def tour(stops, closing="That's 3 stops in all."):
    out = "Step-by-step audio guided tour of Alpha Peak is a driving tour.\n\n"
    for n, st in enumerate(stops, 1):
        title, body = st[0], st[1]
        co = st[2] if len(st) > 2 else f"10.{n}, 100.{n}"
        out += f"Stop {n}: {title}\n\nCoordinates: {co}\n\nType/Specialty: Landmark\n\n{body}\n\nDirections: Go on.\n\n"
    return out + closing + "\n"


def body_of(text, n):
    blocks = rc._stop_blocks(text)
    s, e, _n, _t = blocks[n - 1]
    return text[s:e]


# ── 1. stub tail ──────────────────────────────────────────────────────────────────────────────────────────
def test_stub_reason_function():
    assert t.stub_reason("This site")
    assert t.stub_reason("This site is part of")
    assert t.stub_reason("The statue is 49 meters long.") is None
    assert t.stub_reason("The shrine was rebuilt in 1958 after a landslide") is None          # five words, a verb: only the full stop is missing


def test_body_ending_in_a_stub_is_delivered_without_it_and_logs():
    log = []
    txt = tour([("Alpha Peak", "The statue is 49 meters long and white. The pagoda nearby has halls and colorful paintings of deities. This site"),
                ("Beta Town", K1), ("Gamma Lake", K2)])
    out = t.drop_stub_tails(txt, log.append)
    assert "deities." in out and "deities. This site" not in out
    assert any("stub tail dropped" in m for m in log)
    out2 = s906s.run_pass(txt, None, None)
    assert "This site\n" not in out2


def test_stub_guard_never_empties_a_body():
    txt = tour([("Alpha Peak", "This site"), ("Beta Town", K1), ("Gamma Lake", K2)])
    assert "This site" in t.drop_stub_tails(txt)


def test_join_kept_clauses_never_leaves_a_stub():
    parts, seps = ["This site", "which is bad"], [", and "]
    # the first clause is two words: it is what is left of a cut sentence
    assert rc._join_kept_clauses(parts, seps, lambda p: "bad" in p) == ""
    parts, seps = ["The tower stands by the river", "and the bad clause here"], [", and "]
    out = rc._join_kept_clauses(parts, seps, lambda p: "bad" in p)
    assert out.startswith("The tower") and "bad" not in out


def test_person_cap_rebuild_keeps_short_sentences():
    pl = [{"name": "A", "description": "Cuenin Walter spoke here."},
          {"name": "B", "description": "Father Walter Cuenin spoke here in 2002. Yes, indeed so. The nave is wide and tall and old."},
          {"name": "C", "description": "Father Walter Cuenin returned in 2005. The aisle is long."},
          {"name": "D", "description": "Father Walter Cuenin was praised in 2007. Short one. The font is stone and old."}]
    dg.cap_person_across_stops(pl)
    assert "Short one." in pl[3]["description"] and "Cuenin" not in pl[3]["description"]
    assert "The font is stone and old." in pl[3]["description"]


# ── 2. PERSON-CAP and place words ─────────────────────────────────────────────────────────────────────────
def _pagoda_stops():
    return [
        {"name": "Mountain Pagoda Site", "description": "Linh Son Truong Tho Pagoda sits on the slope and has a large hall with golden roofs."},
        {"name": "Mountain Pagoda Hall", "description": "Linh Son Truong Tho Pagoda holds a unique place in this landscape, not just as a shrine for locals."},
        {"name": "The Reclining Buddha", "description": "The Reclining Buddha Pagoda nearby has several worship halls and colorful paintings. "
                                                      "Linh Son Truong Tho Pagoda is part of a wider landscape that you have glimpsed. The statue is 49 meters long."},
        {"name": "Mountain Summit", "description": "This development replaced the climb through Phan Thiet and Ham Tien by road. The summit is 649 meters high. "
                                                  "Ham Tien lies on the coast. Ham Tien was connected to the highway. Phan Thiet is the nearest city. Phan Thiet grew fast."},
    ]


def test_place_and_common_nouns_are_not_people():
    assert dg._person_names("Linh Son Truong Tho Pagoda holds a unique place.") == set()
    assert dg._person_names("The Reclining Buddha Pagoda nearby has halls.") == set()
    assert dg._person_names("It sits on the Ta Cu Mountain above the coast.") == set()
    # tokens of the tour request / titles are place words even when no landmark noun follows them
    pt = dg.place_tokens_from("a driving tour from the Resort in Ham Tien, Mui Ne", ["Phan Thiet and the River"])
    assert dg._person_names("Ham Tien lies on the coast.", pt) == set()
    assert dg._person_names("Phan Thiet grew fast.", pt) == set()
    assert dg._person_names("Ham Tien lies on the coast.") == {"tien"}      # without the request, only the preposition rule applies
    assert dg._person_names("It lies in Ham Tien on the coast.") == set()   # the object of a place preposition


def test_551_shape_keeps_its_sentences():
    pl = _pagoda_stops()
    before = [p["description"] for p in pl]
    out = dg.cap_person_across_stops(pl, place_text="Create a half day driving tour from a Resort in Ham Tien, Mui Ne")
    assert out == []
    assert [p["description"] for p in pl] == before


def test_original_cuenin_case_still_caps():
    pl = [{"name": "Nave", "description": "Father Walter Cuenin was cheered in the nave in 2002."},
          {"name": "Altar", "description": "Father Walter Cuenin dedicated the altar in 2005. The altar stone came from a quarry nearby."},
          {"name": "Windows", "description": "Father Walter Cuenin chose the glass in 2005. The windows glow at noon each day."},
          {"name": "Organ", "description": "Father Walter Cuenin heard the organ in 2006. The organ has four hundred pipes."}]
    out = dg.cap_person_across_stops(pl, place_text="a church tour")
    assert out and out[0]["person"] == "cuenin"
    assert "Cuenin" not in pl[3]["description"]
    assert "The organ has four hundred pipes." in pl[3]["description"]


# ── 3. ticket / price / guide / listing / filler ──────────────────────────────────────────────────────────
PROMOS = [
    "Visitors can buy tickets for the cable car and access to the mountain, with current prices around $1.95 for entry.",
    "You can buy tickets at the gate.",
    "Tickets cost about 100,000 dong per person.",
    "Prices around $2 apply for the cable car.",
    "The temple charges an admission of a few dollars.",
    "Entry fees are low and the gate opens early.",
    "Visit historic Alpha Peak, Beta orchards, and Gamma summit by cable car with a dedicated English-speaking cultural guide.",
    "Visit the shrine, the market and the lake.",
    "The day trip runs with a private guide who speaks English.",
    "Hikers can join the trail with an English-speaking guide.",
    "Visitors from all over the world come here to experience the quiet of the shrine.",
    "Tourists from around the world visit each summer.",
]


@pytest.mark.parametrize("promo", PROMOS)
def test_every_promo_variant_is_dropped_and_the_real_fact_kept(promo):
    fact = "The shrine was rebuilt in 1958 after a landslide closed the stair."
    txt = tour([("Alpha Peak", f"{K1} {promo} {fact}"), ("Beta Town", K2), ("Gamma Lake", K3)])
    out = s906s.run_pass(txt, None, None)
    assert promo not in out, promo
    assert fact in out and K1 in out


def test_promo_pass_drops_the_last_sentence_too_for_a_refill_to_handle():
    txt = tour([("Alpha Peak", f"{K1} {K2} Visitors can buy tickets for the cable car."), ("Beta Town", K2), ("Gamma Lake", K3)])
    assert "tickets" not in t.run_pass(txt)


def test_fact_with_a_plain_number_is_not_a_price():
    fact = "The tower is 49 meters high and was finished in 1958."
    assert t.promo_reason(fact) is None
    assert t.promo_reason("Pilgrims visit the shrine each spring.") is None


# ── 4. unhedged record ────────────────────────────────────────────────────────────────────────────────────
CLAIM = "At the summit, you see the longest reclining Buddha statue in Asia."
EV552 = "The statue is one of the largest reclining Buddhas in Southeast Asia. It is 49 meters long."
EVENC = "The reclining Buddha statue was the longest in the country up to 2020."


def route_tour(body):
    return tour([("Alpha Lighthouse", K1), ("Beta Town", K2), ("Gamma Mountain", f"You find the mountain above the coast. {body}")])


def test_record_hedged_when_another_stops_evidence_hedges_it():
    ev = {"Gamma Mountain": "The mountain rises 649 meters above the coast.",
          "The Reclining Buddha": EV552 + " The reclining Buddha statue stands on the mountain."}
    out = t.run_pass(route_tour(CLAIM), ev)
    assert "the longest reclining Buddha statue in Asia" not in out
    assert "one of the longest reclining Buddha statues in Asia" in out


def test_record_with_a_temporal_qualification_in_the_encyclopedia_is_hedged_or_dropped():
    ev = {"Gamma Mountain": "The mountain rises 649 meters. The reclining Buddha statue was the longest in the country up to 2020. "
                            "The statue is on the mountain."}
    out = t.run_pass(route_tour(CLAIM), ev)
    assert "the longest reclining Buddha statue in Asia" not in out


def test_record_with_no_evidence_anywhere_is_hedged():
    out = t.run_pass(route_tour(CLAIM), {})
    assert "the longest reclining Buddha statue in Asia" not in out
    assert "one of the longest" in out


def test_record_through_the_906s_last_word_on_the_route_path():
    ev = {"Gamma Mountain": EV552}
    out = s906s.run_pass(route_tour(CLAIM), ev, None)
    assert "the longest reclining Buddha statue in Asia" not in out


def test_comparatives_need_a_supporting_evidence_sentence():
    a = "The statue is even bigger than those at Wat Pho and Wat Lokayasutharam in Thailand."
    b = "The statue is surpassing the famous statues in Thailand."
    for sent in (a, b):
        out = t.run_pass(route_tour(sent), {"Gamma Mountain": "The statue is 49 meters long."})
        assert sent not in out, sent
    ok = {"Gamma Mountain": "The statue is bigger than those at Wat Pho and Wat Lokayasutharam in Thailand."}
    assert a in t.run_pass(route_tour(a), ok)
    ok2 = {"Gamma Mountain": "At 49 meters the statue is surpassing the largest statues in Thailand."}
    assert b in t.run_pass(route_tour(b), ok2)


# ── 5. closing variant ────────────────────────────────────────────────────────────────────────────────────
CLOSERS = [
    "Exploring these sites allows you to connect with the region's heritage and natural beauty, creating lasting memories of your visit.",
    "Visiting these stops lets you see how the coast lives.",
    "Exploring these places helps you understand the region.",
    "The walk ends at the lake, creating lasting memories.",
]


@pytest.mark.parametrize("closer", CLOSERS)
def test_closing_variant_dropped_in_body_and_in_the_tour_closing(closer):
    txt = tour([("Alpha Peak", f"{K1} {K2} {closer}"), ("Beta Town", K2), ("Gamma Lake", K3)])
    assert closer not in s906s.run_pass(txt, None, None)
    txt2 = tour([("Alpha Peak", K1), ("Beta Town", K2), ("Gamma Lake", f"{K3}")], closing=f"{closer} That's 3 stops in all.")
    out2 = s906s.run_pass(txt2, None, None)
    assert closer not in out2 and "That's 3 stops in all." in out2


# ── 6. a neighbour's fact on the wrong stop ───────────────────────────────────────────────────────────────
def test_nearby_you_can_naming_another_stop_is_dropped():
    nb = "Nearby, you can take a cable car up Gamma Mountain, where clouds touch an ancient pagoda."
    txt = tour([("Alpha Lighthouse", f"{K1} {nb} {K2}"), ("Beta Town", K3), ("Gamma Mountain", K1)])
    out = t.run_pass(txt)
    assert nb not in out and K1 in out and K2 in out


def test_nearby_sentence_naming_no_other_stop_is_kept():
    keep = "Nearby, you can see the old harbour wall from the path."
    txt = tour([("Alpha Lighthouse", f"{K1} {keep}"), ("Beta Town", K3), ("Gamma Mountain", K1)])
    assert keep in t.run_pass(txt)


# ── 7. a bearing that contradicts the pin ─────────────────────────────────────────────────────────────────
CITY = (10.9300, 108.1000)


def test_bearing_conflict_dropped_and_agreeing_bearing_kept():
    ok = "You find the mountain about 28 kilometers west of Phan Thiet in the province."
    bad = "You find the mountain just 28 kilometers south of Phan Thiet in the province."
    pin = "10.9400, 107.8500"                         # due west of the city: ~27 km
    for sent, kept in ((ok, True), (bad, False)):
        txt = tour([("Alpha Lighthouse", K1), ("Beta Town", K3), ("Gamma Mountain", f"{K2} {sent}", pin)])
        out = t.drop_pass(txt, None, None, {"Phan Thiet": CITY})
        assert (sent in out) is kept, sent


def test_bearing_function_directly():
    pin = (10.9400, 107.8500)
    assert t.bearing_conflict("The peak is 28 km south of Phan Thiet.", pin, {"phan thiet": CITY})
    assert t.bearing_conflict("The peak is 28 km west of Phan Thiet.", pin, {"phan thiet": CITY}) is None
    assert t.bearing_conflict("The peak is 28 km southwest of Phan Thiet.", pin, {"phan thiet": CITY}) is None   # 45 off, within 60
    assert t.bearing_conflict("The peak is 28 km south of Elsewhere.", pin, {"phan thiet": CITY}) is None        # city unknown


def test_registered_city_centres_are_used():
    t.set_city_centers({"Phan Thiet": CITY})
    bad = "You find the mountain just 28 kilometers south of Phan Thiet."
    txt = tour([("Alpha Lighthouse", K1), ("Beta Town", K3), ("Gamma Mountain", f"{K2} {bad}", "10.9400, 107.8500")])
    assert bad not in t.run_pass(txt)


# ── 8. a coarse pin ───────────────────────────────────────────────────────────────────────────────────────
def test_coarse_pin_replaced_from_a_named_place_geocode():
    pois = [{"name": "Alpha Cham Towers", "coordinates": "10.9000, 108.1000",
             "description": "The towers stand on Ba Nai Hill, 7 kilometers northeast of the city."},
            {"name": "Beta Lighthouse", "coordinates": "10.695960, 107.991340", "description": "A lighthouse."}]
    asked, log = [], []

    def cands(q):
        asked.append(q)
        if "Ba Nai Hill" in q:
            return [{"lat": 10.9552, "lng": 108.1783, "type": "hill"}]
        return []

    fixed = t.fix_coarse_pins(pois, cands, province="Alpha Province", country="Beta", box=(10.5, 11.7, 107.5, 108.7), log=log.append)
    assert fixed == [0]
    assert pois[0]["coordinates"] == "10.955200, 108.178300"
    assert pois[0]["_pin_source_906t"].startswith("geocode:") and "Ba Nai Hill" in pois[0]["_pin_source_906t"]
    assert pois[1]["coordinates"] == "10.695960, 107.991340"          # a precise pin is never touched
    assert any("coarse fallback" in m and "via named-place geocode" in m for m in log)


def test_coarse_pin_kept_when_no_geocode_answers_or_the_hit_is_outside_the_box():
    pois = [{"name": "Alpha Towers", "coordinates": "10.9, 108.1", "description": "Plain text."}]
    log = []
    assert t.fix_coarse_pins(pois, lambda q: [], log=log.append) == []
    assert pois[0]["coordinates"] == "10.9, 108.1" and any("no named-place geocode" in m for m in log)
    far = lambda q: [{"lat": 21.03, "lng": 105.85}]                     # noqa: E731
    assert t.fix_coarse_pins(pois, far, box=(10.5, 11.7, 107.5, 108.7)) == []


def test_a_coarse_looking_hit_is_not_accepted_as_a_replacement():
    pois = [{"name": "Alpha Towers", "coordinates": "10.9, 108.1", "description": "Plain text."}]
    assert t.fix_coarse_pins(pois, lambda q: [{"lat": 10.95, "lng": 108.15}]) == []
