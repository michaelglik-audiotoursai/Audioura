"""LOCAL-906M -- a generic-title user stop is anchored to the tour's place (query + evidence), tour-operator / review
copy, a template closing variant, the destination pin takes the place reference, a Directions block names only its own
leg's end. Offline, $0, generic fixtures (D769); every lookup mocked."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import anchor_evidence_906m as a  # noqa: E402
import delivery_evidence_906h as de  # noqa: E402
import leftovers_906f as f906  # noqa: E402
import refill_quality_906k as k  # noqa: E402
import route_content_896 as rc  # noqa: E402
import route_leftovers_906 as rl  # noqa: E402
import route_order_909 as r909  # noqa: E402
import thin_stop_search as ts  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    r909.clear()
    with rc.job_scope("t906m"):
        rc.set_evidence_904({})
        de.clear()
        yield
    r909.clear()


# ── 1. generic titles and anchors ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("title", ["The cable car ascent", "The summit views and the drive home",
                                   "Dragon fruit country – the plantations along the road", "A walk along the shore"])
def test_generic_titles(title):
    assert a.is_generic_title(title)


@pytest.mark.parametrize("title", ["Peak Mountain", "Arriving at Alpha – the mountain and its legends",
                                   "The Reclining Buddha", "Linh Son Pagoda", "Beta River"])
def test_named_titles_are_not_generic(title):
    assert not a.is_generic_title(title)


TITLES = ["Origin Strand", "Arriving at Alpha Peak – the mountain and its legends", "The cable car ascent",
          "Gamma Pagoda"]


def test_anchors_are_destination_then_neighbouring_named_stops():
    got = a.anchors_for("The cable car ascent", TITLES, destination="Alpha Peak")
    assert got[0] == "Alpha Peak" and "Gamma Pagoda" in got
    assert a.anchors_for("The cable car ascent", TITLES)[0] == "Alpha Peak"      # no destination: the previous named stop
    assert a.anchors_for("Gamma Pagoda", TITLES, destination="Alpha Peak") == []   # a named stop anchors itself


def test_mentions_folds_spelling():
    assert a.mentions("The Tà Cú Mountain cable car", ["Ta Cu Mountain"])
    assert a.mentions("a visit to ta cu", ["Ta Cu Mountain"])
    assert not a.mentions("The Other Peak cable car carries 65 passengers", ["Ta Cu Mountain"])
    assert a.mentions("anything", [])


# ── 2. the search + evidence gate ────────────────────────────────────────────────────────────────────────
OTHER = "https://example.test/other-peak-cable-car"
OURS = "https://example.test/alpha-peak-cable-car"
PAGES = {
    OTHER: "The Other Peak cable car was built in 1955 and carries 65 passengers at a time. " * 4,
    OURS: "The Alpha Peak cable car climbs through the forest to the pagoda near the summit. " * 4,
}


def run_escalation(anchors):
    seen_queries, logs = [], []

    def serp(q):
        seen_queries.append(q)
        return [{"url": OTHER, "title": "Cable car", "snippet": "The cable car ascent of the Other Peak"},
                {"url": OURS, "title": "Cable car", "snippet": "The cable car ascent of Alpha Peak"}]

    rep = ts.escalate_thin_stop(
        "The cable car ascent", "Alpha Peak, Beta Province, Gamma", existing_facts=[], serp_fn=serp,
        fetch_fn=lambda u: PAGES.get(u, ""), llm_fn=lambda *_a: ({"facts": []}, 0, 0),
        escalate_fn=lambda *_a, **_k: {}, wiki_fetch_fn=lambda *_a, **_k: None, log=logs.append,
        anchors=anchors, stop_num=5, use_cache=False)
    return rep, seen_queries, logs


def test_generic_stop_search_carries_the_anchor_and_rejects_the_other_site():
    rep, queries, logs = run_escalation(["Alpha Peak"])
    assert queries and all("alpha peak" in q.lower() for q in queries)
    urls = [p["url"] for p in rep["pages"]]
    assert OURS in urls and OTHER not in urls
    assert any(f"[LOCAL-906M] Stop 5 evidence rejected: no 'Alpha Peak' in {OTHER}" in m for m in logs)
    assert not any("65 passengers" in f["text"] for f in rep["facts"])


def test_a_named_stop_is_searched_as_before():
    rep, queries, logs = run_escalation([])
    assert any(p["url"] == OTHER for p in rep["pages"])
    assert not any("906M" in m for m in logs)


def test_knowledge_fallback_results_without_the_anchor_are_dropped(monkeypatch):
    import stop_knowledge_fallback as skf
    import work_story_searcher as wss
    asked = []

    def fake_serp(q):
        asked.append(q)
        return ([{"snippet": "The Other Peak cable car holds a record.", "url": OTHER, "title": "Other"},
                 {"snippet": "The Alpha Peak cable car opened in 2018.", "url": OURS, "title": "Alpha"}], 0)
    monkeypatch.setattr(wss, "_serp_search", fake_serp)
    ev = skf._web_evidence("The cable car ascent", "Alpha Peak, Beta", focus="place", anchors=["Alpha Peak"])
    assert [e["url"] for e in ev] == [OURS]
    assert all("Alpha Peak" in q for q in asked)


# ── 3. delivery: another site's landmarks in a generic stop's body ───────────────────────────────────────
def tour(stops, closing="That's 3 stops in all."):
    out = "Step-by-step audio guided tour of Alpha Peak is a driving tour.\n\n"
    for n, (title, body, directions) in enumerate(stops, 1):
        out += (f"Stop {n}: {title}\n\nCoordinates: 10.{n}, 100.{n}\n\nType/Specialty: Landmark\n\n{body}\n\n"
                f"Directions: {directions}\n\n")
    return out + closing + "\n"


GENERIC_BODY = ("You board the cable car at the foot of Alpha Peak. The cable car climbs for fifteen minutes through "
                "forest. From the cabin you can see the <Other Waterfall> directly beneath you. At the top, you will "
                "find the <Other Village> and the <Other Bridge>.")


def stops_for(body):
    return [("Origin Strand", "A quiet beach with fishing boats.", "Drive to Alpha Peak."),
            ("The cable car ascent", body, "Walk to the pagoda."),
            ("Gamma Pagoda", "A hillside pagoda with a bell tower.", "Walk back.")]


def test_generic_stop_drops_sentences_naming_landmarks_in_no_evidence():
    ev = {"The cable car ascent": "The cable car at Alpha Peak climbs for fifteen minutes through forest."}
    logs = []
    out = a.drop_other_site_landmarks(tour(stops_for(GENERIC_BODY)), ev, logs.append)
    body = out.split("Stop 2:")[1].split("Directions:")[0]
    assert "Other Waterfall" not in body and "Other Village" not in body and "Other Bridge" not in body
    assert "You board the cable car at the foot of Alpha Peak." in body       # the real fact stays
    assert any("[LOCAL-906M] Stop 2: names" in m for m in logs)


def test_a_landmark_in_the_stops_anchored_evidence_is_kept():
    ev = {"The cable car ascent": "From the cabin you can see the <Other Waterfall> beneath you."}
    out = a.drop_other_site_landmarks(tour(stops_for(GENERIC_BODY)), ev)
    assert "Other Waterfall" in out


def test_a_named_stop_is_untouched():
    st = stops_for(GENERIC_BODY)
    st[1] = ("Peak Cableway", st[1][1], st[1][2])
    out = a.drop_other_site_landmarks(tour(st), {})
    assert "Other Waterfall" in out


def test_the_pass_runs_in_the_delivery_chain():
    out = f906.run_pass(tour(stops_for(GENERIC_BODY)), {"The cable car ascent": "Alpha Peak cable car."}, None)
    assert "Other Village" not in out


# ── 4. promo / review copy and the closing ───────────────────────────────────────────────────────────────
PROMO = [
    "Many tour operators in <Town> heavily advertise trips to the waterfall just outside of town.",
    "Many tour operators in <Town> advertise trips to the pagoda.",
    "You can join private day tours from <Town> that include the pagoda and other local attractions.",
    "You can also join tours that stop here.",
    "Many tours combine a visit here with the nearby market.",
    "The site is open to all, with flexible options available for guided or unguided tours.",
    "The stream is within walking distance from some hotels in <Town>.",
    "If you stay nearby, some hotel rooms offer views of the bay.",
    "Getting to <Peak> was an adventure, and it was worth it.",
    "We loved the quiet courtyard.",
    "I would recommend arriving early.",
]


@pytest.mark.parametrize("sentence", PROMO)
def test_promo_and_review_copy_is_dropped_but_the_fact_stays(sentence):
    fact = "The pagoda was built in 1897 on a rocky island."
    body = f"{fact} {sentence} The bell tower has 184 steps."
    st = [("Origin Strand", "A quiet beach.", "Drive on."), ("Gamma Pagoda", body, "Walk on."),
          ("Delta Hall", "A hall with a tiled roof.", "Walk back.")]
    out = f906.run_pass(tour(st), {}, None)
    seg = out.split("Stop 2:")[1].split("Directions:")[0]
    assert sentence not in seg
    assert fact in seg and "184 steps" in seg


def test_a_real_sentence_with_similar_words_is_kept():
    keep = "The tour of the cellars lasts forty minutes and the guide is a former brewer."
    st = [("Origin Strand", "A quiet beach.", "Drive on."), ("Gamma Pagoda", keep, "Walk on."),
          ("Delta Hall", "A hall.", "Walk back.")]
    assert keep in f906.run_pass(tour(st), {}, None)


@pytest.mark.parametrize("closing", [
    "Together, these stops highlight the stunning natural beauty and cultural significance of coastal attractions.",
    "All in all, these stops showcase the region.",
    "These stops together capture the spirit of the coast.",
    "These stops highlight the heritage of the area.",
    "Across these stops, one thread runs through: the sea.",
])
def test_template_closing_variants_are_dropped(closing):
    t = tour(stops_for("The cable car climbs through forest."), closing=f"{closing} That's 3 stops in all.")
    out = rl.drop_template_closing(t)
    assert closing not in out and "That's 3 stops in all." in out


# ── 5. the destination pin ───────────────────────────────────────────────────────────────────────────────
PLACE_REF = (10.8167, 107.8833)
STREET = (10.928631, 108.088493)               # a street-address geocode ~24 km from the real site
BOX = [10.50, 11.67, 107.49, 108.68]
REQUEST = "Origin Town to Alpha Peak, Beta Province, Gamma"


def poi(name, coords=None):
    p = {"name": name, "coordinates": f"{coords[0]}, {coords[1]}" if coords else "", "type_specialty": "Landmark"}
    if not coords:
        p["_no_coordinate"] = True
    return p


def test_destination_stop_takes_the_place_reference_over_a_street_geocode():
    r909.set_request(REQUEST, "vehicle")
    r909.set_dest_reference(PLACE_REF, "Alpha Peak")
    lst = [poi("Stream", (10.9261, 108.1731)), poi("Gamma Lighthouse", (10.80, 108.05)), poi("Alpha Peak")]
    logs = []
    fixed = r909.restore_pins(lst, [{}, {}, {}], (10.9333, 108.2833), STREET, "Alpha Peak", STREET, BOX, None, logs.append)
    assert fixed == [2]
    assert r909._poi_pin(lst[2]) == pytest.approx(PLACE_REF, abs=1e-5)
    assert any("destination place reference" in m for m in logs)
    assert not any("destination geocode" in m for m in logs)


def test_without_a_place_reference_the_geocode_is_still_the_last_resort():
    r909.set_request(REQUEST, "vehicle")
    lst = [poi("Stream", (10.9261, 108.1731)), poi("Alpha Peak")]
    r909.restore_pins(lst, [{}, {}], (10.9333, 108.2833), STREET, "Alpha Peak", STREET, BOX, None)
    assert r909._poi_pin(lst[1]) == pytest.approx(STREET, abs=1e-5)


def test_the_far_end_of_the_route_is_the_place_reference():
    r909.set_request(REQUEST, "vehicle")
    r909.set_dest_reference(PLACE_REF, "Alpha Peak")
    logs = []
    geo = lambda q: (10.9333, 108.2833) if q.lower().startswith("origin") else STREET  # noqa: E731
    a_, b_ = r909.endpoints_pts(geo, logs.append)
    assert b_ == pytest.approx(PLACE_REF, abs=1e-5)
    assert any("place reference" in m for m in logs)


def test_destination_reference_from_the_area_or_the_906d_retry():
    class Area:
        place_ref_precision, place_ref_lat, place_ref_lng, place_ref_name = "place", 10.8167, 107.8833, "Alpha Peak"
    r909.set_request(REQUEST, "vehicle")
    assert r909.destination_reference(Area(), "Alpha Peak") == pytest.approx(PLACE_REF, abs=1e-5)
    r909.clear()
    r909.set_request(REQUEST, "vehicle")

    class Origin:                                  # the area's reference is the ORIGIN: not the destination's
        place_ref_precision, place_ref_lat, place_ref_lng, place_ref_name = "place", 10.9, 108.2, "Origin Town"
    got = r909.destination_reference(Origin(), "Alpha Peak", lambda d: {"lat": 10.8167, "lng": 107.8833})
    assert got == pytest.approx(PLACE_REF, abs=1e-5) and r909.dest_reference() == got


# ── 6. Directions belong to the leg they start ───────────────────────────────────────────────────────────
def test_a_directions_sentence_naming_a_later_stop_is_dropped():
    st = [("Origin Strand", "A quiet beach.",
           "Head west along the coast road. Continue to Gamma Pagoda — it is roughly 7 km away. "
           "Follow the highway towards Delta Lighthouse, which marks your destination."),
          ("Gamma Pagoda", "A hillside pagoda.", "Take the road inland to Delta Lighthouse."),
          ("Delta Lighthouse", "A red and white lighthouse.", "Walk back to the car.")]
    logs = []
    out = a.trim_directions(tour(st), logs.append)
    d1 = out.split("Directions:")[1].split("\n")[0]
    assert "Gamma Pagoda" in d1 and "Delta Lighthouse" not in d1
    assert "Head west along the coast road." in d1
    assert "Take the road inland to Delta Lighthouse." in out        # the NEXT stop is fine
    assert any("[LOCAL-906M] Stop 1: Directions sentence names a later stop" in m for m in logs)
    assert a.trim_directions(out) == out                              # idempotent


def test_directions_naming_a_name_inside_the_next_title_are_kept():
    st = [("Origin Strand", "A beach.", "Drive to the Alpha Peak Cable Station."),
          ("Alpha Peak Cable Station", "A station.", "Ride up."),
          ("Alpha Peak", "A mountain.", "Walk back.")]
    out = a.trim_directions(tour(st))
    assert "Drive to the Alpha Peak Cable Station." in out


def test_other_landmark_still_flags_unknown_names_for_906k():
    assert k.other_landmark("See the <Other Waterfall> below.", "The cable car ascent", "Alpha Peak") is not None
