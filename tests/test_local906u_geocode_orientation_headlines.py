"""[LOCAL-906U] Offline proof of the 906T Mac findings: geocoder throttle / 429 / cache, failed-lookup pins, the A-to-B Orientation,
headline / operator fragments, the refill bar, one disclosure, dangling start, two distances, colour, "lies from", records, hours,
and the escalated fact. Generic names only (D769). No network, no sleeping."""
import io
import urllib.error

import pytest

import final_906u as u
import nominatim_throttle_906u as t
import pin_fallback_906d as pf
import refill_quality_906k as k
import thin_stop_delivery as tsd


# ── 1. throttle, back-off, cache ─────────────────────────────────────────────────────────────────────────
class Clock:
    def __init__(self):
        self.now, self.sleeps = 100.0, []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def _http429(retry_after=None):
    hdrs = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("http://x", 429, "Too many requests", hdrs, io.BytesIO(b""))


@pytest.fixture
def gate(monkeypatch):
    monkeypatch.setattr(t, "MIN_INTERVAL_S", 1.0)
    monkeypatch.setattr(t, "DEFAULT_BACKOFF_S", 2.0)
    monkeypatch.setattr(t, "_last_request", 0.0)
    t.reset_job()
    return Clock()


def test_requests_are_at_least_one_second_apart_process_wide(gate):
    stamps = []
    for q in ("a", "b", "c"):
        t.call(q, lambda: stamps.append(gate.now) or ["hit"], query=q, sleep=gate.sleep, clock=gate)
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert gaps and all(g >= 1.0 - 1e-9 for g in gaps)


def test_429_honours_retry_after_capped_and_retries_at_most_twice(gate):
    calls = []

    def boom():
        calls.append(gate.now)
        raise _http429(retry_after=999)
    out = t.call("q", boom, query="q", sleep=gate.sleep, clock=gate, log=lambda m: None, empty=[])
    assert out == [] and len(calls) == 3                     # first try + 2 retries, never more
    assert max(gate.sleeps) <= t.RETRY_AFTER_CAP_S
    assert any(abs(s - t.RETRY_AFTER_CAP_S) < 1e-9 for s in gate.sleeps)       # 999 s asked, 30 s waited


def test_429_then_success_returns_the_answer(gate):
    seq = [_http429(retry_after=3), "ok"]

    def f():
        v = seq.pop(0)
        if isinstance(v, Exception):
            raise v
        return v
    logs = []
    assert t.call("q", f, query="q", sleep=gate.sleep, clock=gate, log=logs.append) == "ok"
    assert 3.0 in gate.sleeps and any("retry 1/2" in m for m in logs)


def test_positive_and_negative_answers_are_cached_per_job(gate):
    n = {"c": 0}

    def empty():
        n["c"] += 1
        return None
    for _ in range(3):
        assert t.call("nothing here", empty, query="nothing here", sleep=gate.sleep, clock=gate) is None
    assert n["c"] == 1                                       # a "no such place" answer is cached
    hits = {"c": 0}

    def hit():
        hits["c"] += 1
        return (1.0, 2.0)
    for _ in range(3):
        assert t.call("place", hit, query="place", sleep=gate.sleep, clock=gate) == (1.0, 2.0)
    assert hits["c"] == 1
    t.reset_job()
    t.call("nothing here", empty, query="nothing here", sleep=gate.sleep, clock=gate)
    assert n["c"] == 2                                       # a new job starts clean


def test_geocoder_calls_go_through_the_gate_without_real_network(monkeypatch, gate):
    import geocode_stops as gs
    import urllib.request
    seen = []

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'[{"lat": "10.5", "lon": "107.7", "type": "peak", "category": "natural", "addresstype": "peak", "display_name": "X"}]'
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: seen.append(req.full_url) or R())
    a = gs.geocode_candidates("Some Peak, Province", 5)
    b = gs.geocode_candidates("Some Peak, Province", 5)
    assert a == b and a and len(seen) == 1                   # the second answer came from the job cache


def test_a_failed_geocode_is_logged_as_failed_not_as_no_result(gate):
    t.call("k", lambda: (_ for _ in ()).throw(_http429()), query="Alpha Mountain, Province", sleep=gate.sleep, clock=gate,
           log=lambda m: None)
    assert t.lookup_failed_for("Alpha Mountain") is True
    assert t.lookup_failed_for("Beta Statue") is False


# ── 1b. a failed-lookup stop does not inherit another stop's pin ─────────────────────────────────────────
BOX = [10.5, 11.5, 107.5, 108.5]
REF = (10.936, 108.146)


def _pois():
    return [{"name": "Alpha Mountain", "coordinates": "10.9360, 108.1460", "coord_source": "user_share_link"},
            {"name": "Beta Lighthouse", "coordinates": "10.4075, 108.4585"}]


def test_a_stop_whose_own_lookups_failed_stays_unpinned_and_logs_it(gate):
    t.call("k", lambda: (_ for _ in ()).throw(_http429()), query="Beta Lighthouse, Province, Country", sleep=gate.sleep,
           clock=gate, log=lambda m: None)
    pois, logs = _pois(), []
    rows = [{"snapped": True, "new_coordinate": REF, "reference": REF}, {"snapped": False, "reference": None}]
    moved = pf.last_resort_pins(pois, rows, BOX, (11.0, 108.0), "Province", log=logs.append)
    assert moved == []
    assert pois[1].get("_no_coordinate") and pois[1].get("coordinates_approximate")
    assert pois[1].get("_pin_moved_to_stop") is None
    assert any("[LOCAL-906U]" in m and "did not inherit".replace("did not", "does not") in m for m in logs), logs


def test_a_stop_with_no_result_but_no_error_still_follows_the_old_rule(gate):
    pois, logs = _pois(), []
    rows = [{"snapped": True, "new_coordinate": REF, "reference": REF}, {"snapped": False, "reference": None}]
    moved = pf.last_resort_pins(pois, rows, BOX, (11.0, 108.0), "Province", log=logs.append)
    assert moved == [1]                                      # unchanged behaviour when the geocoder simply knew nothing


# ── 2. the A-to-B Orientation ────────────────────────────────────────────────────────────────────────────
AB = (
    "Step-by-step audio guided tour from Origin Town to Dest Mountain in Some Province, Country - driving tour.\n\n"
    "Stop 1: First Towers\n\nCoordinates: 10.9, 108.1\n\nType/Specialty: Historical site\n\n"
    "Orientation: Each stop on this journey reveals how the ancient reverence for spiritual sites coexists with the present. "
    "Your first stop is First Towers. Leave Dest Mountain and head northwest on the main road, then turn right onto Route 1. "
    "Continue for about 30 kilometers until you reach the First Towers. Along the way, you'll see rice fields. "
    "The route starts at Origin Town; from there, head to First Towers.\n\n"
    "The three towers of First stand on a hill.\n\nDirections: From Origin Town, head to First Towers.\n\n"
    "Stop 2: Dest Mountain\n\nCoordinates: 10.8, 107.8\n\nType/Specialty: Natural attraction\n\nDest Mountain rises above the plain.\n\n"
    "That's 2 stops in all.\n")


def test_ab_orientation_starts_at_the_origin_one_route_sentence():
    logs = []
    out = u.fix_ab_orientation(AB, log=logs.append)
    ori = [ln for ln in out.split("\n") if ln.startswith("Orientation:")][0]
    assert "Leave Dest Mountain" not in ori and "Continue for about 30" not in ori and "Along the way" not in ori
    assert "Each stop on this journey" not in ori
    assert ori.count("The route starts at Origin Town") == 1
    assert "Your first stop is First Towers." in ori
    assert any("leave the destination" in m for m in logs) and any("template" in m for m in logs)


def test_ab_orientation_synthesises_the_route_sentence_when_the_model_wrote_none():
    text = AB.replace(" The route starts at Origin Town; from there, head to First Towers.", "")
    ori = [ln for ln in u.fix_ab_orientation(text).split("\n") if ln.startswith("Orientation:")][0]
    assert ori.endswith("The route starts at Origin Town; from there, head to First Towers.")


def test_ab_orientation_leaves_a_clean_orientation_alone():
    clean = AB.replace("Each stop on this journey reveals how the ancient reverence for spiritual sites coexists with the present. ", "") \
        .replace("Leave Dest Mountain and head northwest on the main road, then turn right onto Route 1. ", "") \
        .replace("Continue for about 30 kilometers until you reach the First Towers. Along the way, you'll see rice fields. ", "")
    assert u.fix_ab_orientation(clean) == clean


def test_a_non_ab_tour_is_not_touched():
    text = AB.replace("tour from Origin Town to Dest Mountain in Some Province", "walking tour of Some Province")
    assert u.fix_ab_orientation(text) == text


# ── 3. headlines / operator copy ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", [
    "Discover Alpha Lighthouse & Cable Car to Beta Peak.",
    "Alpha Lighthouse & Beta Mountain Tour.",
    "You can find recommended routes and expert travel tips to help plan your visit.",
    "Beta Mountain Day Trip.",
    "Alpha Pagoda Tour Package.",
    "Explore Alpha Pagoda Beta Mountain Cable Car.",
    "Book Alpha Pagoda Beta Mountain Experience.",
])
def test_headline_and_operator_variants_are_dropped(x):
    assert u.headline_reason(x), x


@pytest.mark.parametrize("x", [
    "The lighthouse rises 65 meters above the sea.",
    "Visitors explore the pagoda and its gardens at dawn.",
    "Discover the quiet courtyard behind the main hall.",
    "The tour guides tell the story of the founder.",
])
def test_real_sentences_are_not_headlines(x):
    assert u.headline_reason(x) is None, x


def test_a_real_fact_in_the_same_stop_is_kept():
    text = ("Tour\n\nStop 1: Alpha Lighthouse\n\nCoordinates: 1, 2\n\nType/Specialty: Lighthouse\n\n"
            "The lighthouse was built in 1897. Discover Alpha Lighthouse & Cable Car to Beta Peak. Alpha Lighthouse & Beta Mountain Tour.\n\n"
            "That's 1 stop in all.\n")
    out = u.sentence_pass(text, {"Alpha Lighthouse": "The lighthouse was built in 1897."})
    assert "built in 1897" in out and "&" not in out


# ── 4. the refill bar on every path ──────────────────────────────────────────────────────────────────────
BEACH = "Wander the beautiful beaches in this relaxing area."


def test_a_landform_the_stop_is_not_is_rejected_even_from_its_own_evidence():
    why = k.refill_reject(BEACH, "Alpha Mountain Pagoda", None, "article", "Buddhist Temple", True)
    assert why and "landform" in why
    assert k.refill_reject(BEACH, "Alpha Mountain Pagoda", None, "snippet", "Buddhist Temple", True)
    assert k.refill_reject("Alpha Beach is a long sandy beach.", "Alpha Beach", None, "article", "Beach", True) is None


def test_the_bar_pass_drops_a_verbatim_evidence_sentence_that_fails_it():
    text = ("Tour\n\nStop 1: Alpha Mountain Pagoda\n\nCoordinates: 1, 2\n\nType/Specialty: Buddhist Temple\n\n"
            f"Alpha Mountain Pagoda was rebuilt after the war. {BEACH}\n\nThat's 1 stop in all.\n")
    ev = {"Alpha Mountain Pagoda": f"Alpha Mountain Pagoda was rebuilt after the war. {BEACH}"}
    logs = []
    out = u.bar_pass(text, ev, logs.append)
    assert "beaches" not in out and "rebuilt after the war" in out
    assert any("refill bar" in m for m in logs)


# ── 5. one disclosure ────────────────────────────────────────────────────────────────────────────────────
DISC = ("We could not confirm verified historical details for this stop, so this part of the tour focuses on what you can see and "
        "sense here rather than on dates or events.")


def test_one_disclosure_per_stop_even_as_its_own_paragraph_on_the_last_stop():
    text = ("Tour\n\nStop 1: A\n\nCoordinates: 1, 2\n\nType/Specialty: x\n\nLook out. " + DISC + "\n\nDirections: Walk on to B.\n\n"
            "Stop 2: B\n\nCoordinates: 1, 2\n\nType/Specialty: x\n\nLook out at the view. " + DISC + "\n\n" + DISC +
            "\n\nThat's 2 stops in all.\n")
    out = u.one_disclosure(text)
    assert out.count("We could not confirm") == 2
    assert out.split("Stop 2: B")[1].count("We could not confirm") == 1
    assert "That's 2 stops in all." in out


# ── 6. dangling start ────────────────────────────────────────────────────────────────────────────────────
def test_among_its_at_the_start_of_a_stop_names_the_title():
    assert u.fix_dangling_its("Among its notable features is the pagoda.", "Alpha Mountain") == \
        "Among Alpha Mountain's notable features is the pagoda."
    assert u.fix_dangling_its("Among its notable features is the pagoda.", "Cape Atlas") == \
        "Among Cape Atlas' notable features is the pagoda."
    assert u.fix_dangling_its("Among its notable features is the pagoda.", "Mount Eros") == \
        "Among Mount Eros' notable features is the pagoda."
    assert u.fix_dangling_its("The pagoda is old.", "Alpha Mountain") is None


def test_dangling_its_is_fixed_only_on_the_first_sentence():
    text = ("Tour\n\nStop 1: Alpha Mountain\n\nCoordinates: 1, 2\n\nType/Specialty: x\n\n"
            "The peak is 600 m high. Among its notable features is the pagoda.\n\nThat's 1 stop in all.\n")
    assert "Among its notable" in u.sentence_pass(text, {})


# ── 7. two distances ─────────────────────────────────────────────────────────────────────────────────────
def test_two_distances_from_one_city_reduced_to_the_first_without_an_encyclopedia():
    text = ("Tour\n\nStop 1: Alpha Mountain\n\nCoordinates: 1, 2\n\nType/Specialty: x\n\n"
            "The mountain is just off the highway, 31km southwest of Beta City. Alpha Mountain is 28 km west of Beta City, in Gamma Province.\n\n"
            "That's 1 stop in all.\n")
    out = u.sentence_pass(text, {})
    assert "31km southwest" in out and "28 km" not in out


def test_two_distances_keep_the_encyclopedias_value_when_one_is_an_article_sentence(monkeypatch):
    text = ("Tour\n\nStop 1: Alpha Mountain\n\nCoordinates: 1, 2\n\nType/Specialty: x\n\n"
            "The mountain is just off the highway, 31km southwest of Beta City. Alpha Mountain is 28 km west of Beta City, in Gamma Province.\n\n"
            "That's 1 stop in all.\n")
    monkeypatch.setattr(k, "source_of", lambda cand, blob, title: "article" if "28 km" in cand else "snippet")
    out = u.sentence_pass(text, {"Alpha Mountain": "Alpha Mountain is 28 km west of Beta City, in Gamma Province."})
    assert "28 km west" in out and "31km" not in out


# ── 8. colour and "From the vehicle" ─────────────────────────────────────────────────────────────────────
STAT = "From the vehicle, you see the statue's golden surface stretch along the hillside, catching sunlight with a soft gleam."


def test_a_colour_the_evidence_contradicts_or_does_not_carry_is_dropped():
    assert u.colour_reason(STAT, "The statue is white and 49 meters long.").startswith("sensory colour 'gold' contradicts")
    assert u.colour_reason(STAT, "The statue is 49 meters long.")
    assert u.colour_reason(STAT, "The statue is gilded gold and 49 meters long.") is None
    assert u.colour_reason("The statue is 49 meters long.", "") is None


def test_from_the_vehicle_is_not_used_after_a_walk():
    text = ("Tour\n\nStop 1: Alpha Pagoda\n\nCoordinates: 1, 2\n\nType/Specialty: x\n\nThe pagoda is old.\n\nDirections: Walk on to the statue.\n\n"
            "Stop 2: The Statue\n\nCoordinates: 1, 2\n\nType/Specialty: x\n\n"
            "From the vehicle, you see the statue stretch along the hillside. The statue is 49 meters long.\n\nThat's 2 stops in all.\n")
    out = u.sentence_pass(text, {"The Statue": "The statue is 49 meters long."})
    assert "From the vehicle" not in out and "From here, you see the statue" in out
    drive = text.replace("Walk on to the statue", "Drive on to the statue")
    assert "From the vehicle" in u.sentence_pass(drive, {"The Statue": "The statue is 49 meters long."})


# ── 9. "lies from" ───────────────────────────────────────────────────────────────────────────────────────
def test_lies_from_without_a_measure_is_a_fragment():
    assert u.lies_from_fragment("The statue lies from the tram's summit station, inviting visitors to traverse the final stretch.")
    assert u.lies_from_fragment("The tower stands from the old gate.")
    assert not u.lies_from_fragment("The statue lies 400 meters from the tram's summit station.")
    assert not u.lies_from_fragment("The statue is made from white stone.")


# ── 10. the apposition record ────────────────────────────────────────────────────────────────────────────
REC = "You stand near Alpha Lighthouse, the tallest lighthouse in Vietnam, rising 65 meters on a rocky island."


def test_tallest_in_country_apposition_is_hedged_when_the_evidence_does_not_carry_it():
    out = u._hedge_record(REC, "The lighthouse is 65 meters high.", "Alpha Lighthouse")
    assert out and "one of the tallest lighthouses in Vietnam" in out
    assert u._hedge_record(REC, "Alpha Lighthouse is the tallest lighthouse in Vietnam.", "Alpha Lighthouse") is None


# ── 11. hours copy ───────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", [
    "The Reclining Buddha on Alpha Mountain is open all year round.",
    "The cable car opens at 8:00 am.",
    "The pagoda is open daily.",
    "Opening hours vary by season.",
    "The garden is closed on Mondays.",
])
def test_hours_copy_is_dropped(x):
    assert u.hours_reason(x), x


@pytest.mark.parametrize("x", ["The doors are open to the courtyard.", "The statue was built in 1958.", "She opened the shutters."])
def test_a_real_sentence_is_not_hours_copy(x):
    assert u.hours_reason(x) is None, x


# ── 12. the escalated fact survives, or its drop is logged ───────────────────────────────────────────────
FACT = "The cable car climbs at an incline of 37 degrees."


def test_a_short_sourced_fact_can_be_narrated_back():
    logs = []
    sents, rep = tsd.narrate_stop_body(
        "The cable car ascent", [FACT], "", "Alpha Mountain",
        narrate_fn=lambda sysmsg, user, model: ({"sentences": ["The cable car climbs at an angle of 37 degrees."]}, 10, 10),
        min_sentences=1, max_sentences=3, log=logs.append)
    assert sents == ["The cable car climbs at an angle of 37 degrees."], logs


def test_a_sentence_with_a_number_the_fact_does_not_state_is_still_rejected():
    logs = []
    sents, rep = tsd.narrate_stop_body(
        "The cable car ascent", [FACT], "", "Alpha Mountain",
        narrate_fn=lambda sysmsg, user, model: ({"sentences": ["The ride climbs 45 degrees."]}, 10, 10),
        min_sentences=1, max_sentences=3, log=logs.append)
    assert sents is None
    assert any("not traceable" in m for m in logs) and any("[LOCAL-906U]" in m and "not narrated" in m for m in logs)


def test_lead_job_backoff_budget_caps_total_429_sleep(monkeypatch):
    """[LEAD 906U] persistent 429s must not stall a job: total back-off per job is capped."""
    import nominatim_throttle_906u as t
    t.reset_job()
    monkeypatch.setattr(t, "DEFAULT_BACKOFF_S", 2.0)
    slept = []

    class E429(Exception):
        code = 429
        headers = {"Retry-After": "30"}

    def boom():
        raise E429("Too many requests")

    for i in range(10):
        t.call(("q", i), boom, query=f"place {i}", sleep=slept.append, min_interval=0.0, log=lambda m: None)
    assert sum(slept) <= t.JOB_BACKOFF_BUDGET_S + 1e-9
    t.reset_job()
    assert t._backoff_spent[0] == 0.0
