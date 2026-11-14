"""[LOCAL-906V] drive quality and repeats. Generic names only (D769), offline."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drive_quality_906v as v  # noqa: E402
import final_906u as u  # noqa: E402
import language_dest_906s as s906  # noqa: E402
import leftovers_906c as c  # noqa: E402
import route_order_909 as r  # noqa: E402

DISC = ("We could not confirm verified historical details for this stop, so this part of the tour focuses on what you can see "
        "and sense here rather than on dates or events.")


def tour(stops, closing="That's {n} stops in all.\n\nIf you would like to eat nearby we can build you a restaurant tour.\n"):
    out = ["Step-by-step audio guided tour from Alpha Town to Omega Mountain in Region, Country - driving tour.\n"]
    for k, (title, body, dirs) in enumerate(stops, 1):
        out.append(f"Stop {k}: {title}\n\nAddress: x\n\nCoordinates: 10.0, 108.0\n\nType/Specialty: Historical site\n\n{body}\n")
        if dirs:
            out.append(f"Directions: {dirs}\n")
    out.append(closing.format(n=len(stops)))
    return "\n".join(out)


def log_to(buf):
    return lambda m: buf.append(m)


def body_of(text, num):
    blk = text.split(f"Stop {num}:")[1].split("\nStop ")[0]
    return blk


# ── 1. a sensory-only stop ──────────────────────────────────────────────────────────────────────────────
SENSE = "Around you, the sound of rustling leaves and distant birdcalls mix with the faint scent of dry earth, anchoring these ancient stones in the living landscape."


def test_sensory_sentence_is_not_a_fact():
    assert v.sensory_only(SENSE)
    assert not s906._factual(SENSE)
    assert not v.sensory_only("The towers were built in 1280 by the Beta kingdom.")
    assert not v.sensory_only("From here you can see Mount Gamma rising behind the old gate.")


def test_sensory_only_stop_gets_the_disclosure_when_no_refill():
    t = tour([("Alpha Towers", SENSE, "Walk on to Beta Dunes."), ("Beta Dunes", "The dunes cover about 40 square kilometres of pale sand.", "")])
    buf = []
    out = v.last_word(t, {}, log_to(buf))
    assert "could not confirm verified historical details" in body_of(out, 1)
    assert SENSE not in out
    assert "dunes cover about 40 square" in body_of(out, 2)
    assert any("no-history disclosure" in m for m in buf)


def test_sensory_only_stop_gets_a_refill_from_its_evidence():
    ev = {"Alpha Towers": "Alpha Towers are three brick towers on a hill seven kilometres northeast of Alpha Town. "
                          "The towers were built by the Cham kingdom between the eighth and thirteenth centuries."}
    t = tour([("Alpha Towers", SENSE, "Walk on to Beta Dunes."), ("Beta Dunes", "The dunes cover about 40 square kilometres of pale sand.", "")])
    out = v.last_word(t, ev, lambda m: None)
    b1 = body_of(out, 1)
    assert "three brick towers" in b1 or "Cham kingdom" in b1, b1


# ── 2. backtrack ───────────────────────────────────────────────────────────────────────────────────────
A, B = (10.00, 108.30), (10.00, 107.80)           # origin east, destination 55 km west


def test_backtrack_reason_on_the_behind_the_origin_stop():
    prev = (10.05, 108.20)                           # stop 1, 10 km before the origin
    behind = (10.00, 108.35)                         # behind the origin, east of it
    nxt = B
    why = v.backtrack_reason(prev, behind, nxt, A, B)
    assert why and "behind the origin" in why
    on_way = (10.02, 108.00)
    assert v.backtrack_reason(prev, on_way, nxt, A, B) is None


def test_backtrack_stop_replaced_from_pool_and_logged():
    pl = [{"name": "Stop One", "coordinates": "10.0500, 108.2000"},
          {"name": "Behind Dunes", "coordinates": "10.0000, 108.3500"},
          {"name": "Omega Mountain", "coordinates": "10.0000, 107.8000"}]
    pool = [{"name": "Mid Pagoda", "coordinates": "10.0100, 108.0000"}]
    buf = []
    out = v.replace_backtracks(pl, A, B, pool, "Omega Mountain", None, log_to(buf))
    assert [p["name"] for p in out] == ["Stop One", "Mid Pagoda", "Omega Mountain"]
    assert any("[LOCAL-906V] backtrack stop rejected" in m for m in buf)


def test_backtrack_stop_dropped_without_pool_but_never_below_two():
    pl = [{"name": "Stop One", "coordinates": "10.0500, 108.2000"},
          {"name": "Behind Dunes", "coordinates": "10.0000, 108.3500"},
          {"name": "Omega Mountain", "coordinates": "10.0000, 107.8000"}]
    out = v.replace_backtracks(pl, A, B, [], "Omega Mountain", None, None)
    assert [p["name"] for p in out] == ["Stop One", "Omega Mountain"]
    two = [{"name": "Behind Dunes", "coordinates": "10.0000, 108.3500"}, {"name": "Omega Mountain", "coordinates": "10.0000, 107.8000"}]
    assert len(v.replace_backtracks(two, A, B, [], "Omega Mountain", None, None)) == 2


def test_order_poi_list_applies_the_backtrack_guard():
    r._STATE.clear()
    r.set_request("Alpha Town to Omega Mountain, Region, Country", "driving")
    pins = {"Alpha Town": A, "Omega Mountain": B}
    pl = [{"name": "Stop One", "coordinates": "10.0500, 108.2000"},
          {"name": "Behind Dunes", "coordinates": "10.0000, 108.3500"},
          {"name": "Omega Mountain", "coordinates": "10.0000, 107.8000"}]
    pool = [{"name": "Mid Pagoda", "coordinates": "10.0100, 108.0000"}]
    buf = []
    out = r.order_poi_list(pl, geocode_fn=lambda q: pins.get(q.split(",")[0].strip()), log=log_to(buf), pool=pool)
    assert "Behind Dunes" not in [p["name"] for p in out]
    assert any("backtrack stop rejected" in m for m in buf)
    r.clear()


def test_failed_endpoint_lookup_is_not_cached():
    r._STATE.clear()
    r.set_request("Alpha Town to Omega Mountain, Region, Country", "driving")
    assert r.endpoints_pts(lambda q: None) == (None, None)
    pins = {"Alpha Town": A, "Omega Mountain": B}
    a, b = r.endpoints_pts(lambda q: pins.get(q.split(",")[0].strip()))
    assert a == A and b == B
    r.clear()


# ── 3. Directions of the wrong leg ──────────────────────────────────────────────────────────────────────
def test_directions_name_the_leg_to_the_next_stop():
    t = tour([
        ("Alpha Towers", "The towers were built in 1280 by the Beta kingdom.",
         "From Alpha Town, head to Alpha Towers. Start by heading south from Alpha Towers. Continue along the highway, and soon you will see signs "
         "for Beta Dunes, where you turn right to reach your destination."),
        ("Beta Dunes", "The dunes cover about 40 square kilometres of pale sand.",
         "From Alpha Towers, head southeast on the coast road, then turn right onto the highway. Continue for about 20 kilometers to reach Omega Mountain."),
        ("Omega Mountain", "The mountain rises 649 metres above sea level.", ""),
    ])
    buf = []
    out = v.directions_pass(t, log_to(buf))
    assert "to reach Beta Dunes" in out and "reach your destination" not in out
    assert "From Alpha Towers, head southeast" not in out
    assert "From here, head southeast on the coast road" in out
    assert "From Alpha Town, head to Alpha Towers." in out          # the origin lead of stop 1 stays


def test_loose_destination_sentence_dropped_when_it_names_nothing():
    t = tour([("Alpha Towers", "The towers were built in 1280 by the Beta kingdom.",
               "Head south along the coast. Turn off to the right to reach your destination."),
              ("Beta Dunes", "The dunes cover about 40 square kilometres.", ""),
              ("Omega Mountain", "The mountain rises 649 metres.", "")])
    out = v.directions_pass(t, None)
    assert "your destination" not in out and "Head south along the coast." in out


# ── 4. copy ───────────────────────────────────────────────────────────────────────────────────────────
def test_copy_variants_dropped_and_the_fact_kept():
    body = ("The White Dunes cover about 40 square kilometres of pale sand. "
            "Many visitors take day tours from Capital City to see both the red and the white dunes. "
            "If you travel about 40 minutes from here, you reach Omega Mountain, another popular destination. "
            "The dunes are a unique and breathtaking landscape that many find unforgettable, especially at sunset.")
    t = tour([("Beta Dunes", body, ""), ("Omega Mountain", "The mountain rises 649 metres above sea level.", "")])
    buf = []
    out = v.sentence_pass(t, log_to(buf))
    b = body_of(out, 1)
    assert "cover about 40 square kilometres" in b
    assert "day tours" not in b and "another popular destination" not in b and "unforgettable" not in b
    assert len(buf) == 3


def test_closing_family_dropped_with_no_fact_kept_with_one():
    gone = "Experiencing the breathtaking landscapes and ancient structures invites a deeper appreciation for the rich heritage of this area."
    kept = "Visiting the museum gives you access to 120 original manuscripts from the 14th century."
    assert v.copy_reason(gone)
    assert v.copy_reason("Exploring these places helps you see the region differently.")
    assert v.copy_reason("Discovering the dunes lets you feel the wind.")
    assert not v.copy_reason(kept)
    t = tour([("Beta Dunes", "The dunes cover about 40 square kilometres of pale sand.", ""),
              ("Omega Mountain", "The mountain rises 649 metres above sea level. " + gone, "")],
             closing="{n} stops. That's 2 stops in all.\n")
    out = v.sentence_pass(t, None)
    assert "invites a deeper appreciation" not in out and "rises 649 metres" in out


# ── 5. the thread template in a body ────────────────────────────────────────────────────────────────────
def test_thread_template_dropped_from_a_body_not_from_the_fact():
    thread = "Across these stops, one thread runs through: the places that shape Omega Mountain and Beta Dunes."
    t = tour([("Alpha Towers", "The towers were built in 1280 by the Beta kingdom. " + thread, "Walk on to Beta Dunes."),
              ("Beta Dunes", "The dunes cover about 40 square kilometres.", "")])
    out = v.sentence_pass(t, None)
    assert "one thread runs through" not in out and "built in 1280" in out


def test_conclusion_salvage_never_returns_the_thread_template():
    import tour_conclusion as tc
    t = tour([("Alpha Towers", "The towers were built in 1280 by the Beta kingdom.", ""), ("Beta Dunes", "The dunes cover about 40 square kilometres.", "")],
             closing="That's 2 stops in all.\n\nIf you would like to eat nearby we can build you a restaurant tour.\n\n"
                     "Across these stops, one thread runs through: the places that shape Alpha Towers.\n")
    out = tc.rebuild_conclusion(t, venue_name="Alpha Towers and Beta Dunes")
    first_stop = out.split("Stop 2:")[0]
    assert "one thread runs through" not in first_stop
    assert "one thread runs through" not in body_of(out, 2).split("Directions")[0].split("Type/Specialty")[1].split("\n\n", 1)[1][:80]


# ── 6. a distance told twice, an appended location lead ────────────────────────────────────────────────
def test_same_value_distance_is_one_fact():
    body = ("Omega Mountain stands 649 metres above sea level and is about 28 kilometers west of Gamma City. "
            "You can reach the top by cable car. "
            "Omega Mountain is 28 km west of Gamma City, in Gamma Province, Southern Region, Country.")
    t = tour([("Beta Dunes", "The dunes cover about 40 square kilometres.", ""), ("Omega Mountain", body, "")])
    buf = []
    out = u.sentence_pass(t, {}, log_to(buf))
    b = body_of(out, 2)
    assert b.count("28 k") == 1
    assert "about 28 kilometers west" in b and "in Gamma Province" not in b
    assert any("told twice" in m for m in buf)


def test_refill_candidate_repeating_a_stated_distance_is_refused():
    cur = ["Omega Mountain stands 649 metres above sea level and is about 28 kilometers west of Gamma City."]
    assert v.distance_duplicate("Omega Mountain is 28 km west of Gamma City, in Gamma Province, Country.", cur)
    assert not v.distance_duplicate("Omega Mountain is 31 km west of Gamma City, in Gamma Province, Country.", cur)
    assert not v.distance_duplicate("Omega Mountain has two pagodas.", cur)


def test_thin_refill_does_not_append_a_stated_distance():
    import leftovers_906f as f
    ev = {"Omega Mountain": "Omega Mountain is 28 km west of Gamma City, in Gamma Province, Southern Region, Country."}
    t = tour([("Beta Dunes", "The dunes cover about 40 square kilometres of pale sand.", ""),
              ("Omega Mountain", "Omega Mountain is about 28 kilometers west of Gamma City.", "")])
    out = f.refill_thin_stops(t, ev, None)
    assert body_of(out, 2).count("28 k") == 1


# ── 7. a legend told once ──────────────────────────────────────────────────────────────────────────────
def test_legend_told_three_times_is_told_once():
    body = ("You are at Linh Pagoda, located on the hill above the town. "
            "The pagoda is associated with a healing legend involving Empress Dowager Tu Du. "
            "Because of this healing story, Emperor Tu Duc gave royal recognition to the pagoda. "
            "The pagoda has been restored over time, giving it a nearly new appearance today. "
            "Linh Pagoda was conferred royal recognition by Emperor Tu Duc after Master Tran Huu Duc successfully treated Empress Dowager Tu Du. "
            "Linh Pagoda is steeped in a legend of healing that is still passed down among the locals.")
    t = tour([("Alpha Towers", "The towers were built in 1280 by the Beta kingdom.", ""), ("Linh Pagoda", body, "")])
    buf = []
    out = v.retold_pass(t, log_to(buf))
    b = body_of(out, 2)
    assert "conferred royal recognition by Emperor Tu Duc after Master" in b
    assert "associated with a healing legend" not in b and "Because of this healing story" not in b and "steeped in a legend" not in b
    assert "restored over time" in b and "located on the hill" in b
    assert len([m for m in buf if "told again" in m]) == 3


def test_two_different_events_are_both_kept():
    body = ("The tower was built in 1280 by the Beta kingdom. The tower was damaged by an earthquake in 1855 and restored by local families. "
            "A small museum beside the gate shows old coins and pottery.")
    t = tour([("Alpha Towers", body, ""), ("Omega Mountain", "The mountain rises 649 metres.", "")])
    assert v.retold_pass(t, None) == t


# ── the pass is idempotent and a clean tour is untouched ─────────────────────────────────────────────────
def test_clean_tour_unchanged():
    t = tour([("Alpha Towers", "The towers were built in 1280 by the Beta kingdom. They stand on a hill above the river.", "Walk on to Beta Dunes."),
              ("Beta Dunes", "The dunes cover about 40 square kilometres of pale sand.", "")])
    assert v.run_pass(t, None) == t
    once = v.run_pass(tour([("Alpha Towers", SENSE + " The towers were built in 1280.", "")]), None)
    assert v.run_pass(once, None) == once


def test_closing_paragraph_template_goes_but_the_count_stays():
    gone = "Experiencing the breathtaking landscapes and ancient structures invites a deeper appreciation for the rich heritage."
    t = tour([("Beta Dunes", "The dunes cover about 40 square kilometres of pale sand.", ""),
              ("Omega Mountain", "The mountain rises 649 metres above sea level.", "")],
             closing=gone + " That's 2 stops in all.\n\nIf you would like to eat nearby we can build you a restaurant tour.\n")
    out = v.run_pass(t, None)
    assert "invites a deeper appreciation" not in out
    assert "That's 2 stops in all." in out and "restaurant tour" in out and "rises 649 metres" in out


def test_same_value_distance_fixture_through_last_word_order():
    # 906U runs first, 906V after it: the pair is already one fact by then and 906V leaves it alone
    body = "Omega Mountain is about 28 kilometers west of Gamma City. You can reach the top by cable car."
    t = tour([("Beta Dunes", "The dunes cover about 40 square kilometres.", ""), ("Omega Mountain", body, "")])
    assert v.run_pass(u.run_pass(t, {}, None), None) == u.run_pass(t, {}, None)


def test_lead_wave57_breadcrumb_label_dropped():
    """[LEAD wave 57] '<Country>/<Province>/<Place> 1.' at the end of a body is a gallery label; slashes in prose stay."""
    import drive_quality_906v as v
    body = ("Stop 6: Some Pagoda\n\nType/Specialty: Buddhist temple\n\n"
            "The pagoda was restored over time. It is a pilgrimage site. Countryland/Some Province/Some Pagoda 1.\n\n"
            "Directions: Walk on.")
    out = v.strip_breadcrumbs(body)
    assert "Countryland/Some Province" not in out
    assert "It is a pilgrimage site." in out
    assert "Type/Specialty: Buddhist temple" in out
    prose = "Stop 1: X\n\nThe road climbs at 40 km/h limits and the river and/or canal meet here."
    assert v.strip_breadcrumbs(prose) == prose
    alone = "Stop 1: X\n\nCountryland/Some Province/Some Pagoda\n\nA fact here."
    assert "Countryland/" not in v.strip_breadcrumbs(alone)


def test_lead_wave58_travel_clause_cut_never_leaves_a_fragment():
    """[LEAD wave 58] 897's clause cut left 'This cable car system, designed in Austria.' (no main verb); 906E then glued the title on."""
    import route_content_896 as r
    assert r._cut_left_np("This cable car system, designed in Austria.")
    assert not r._cut_left_np("The cable car system was designed in Austria.")
    assert not r._cut_left_np("The pagoda, built in 1872, is the older of the two.")


def test_lead_wave58_final_sweep_price_lone_clause_advice():
    """[LEAD wave 58] the cloud miss: a price in words; plus a lone 'If ...' clause and visiting advice. Real facts stay."""
    import drive_quality_906v as v
    t = ("Stop 3: Fruit country\n\nType/Specialty: Agricultural tourism\n\n"
         "Farmers grow the fruit here. You can find the fruit here sold at about 0.90 US dollars per kilogram.\n\n"
         "Stop 5: The ascent\n\nThe system was designed in Austria. If you take this cable car. "
         "It is recommended to visit early in the morning. In 1802 Dong Nai became a province. The statue weighs 200 pounds.\n\n"
         "Directions: Walk on.")
    out = v.final_sweep(t)
    assert "US dollars" not in out and "If you take this cable car." not in out and "recommended to visit" not in out
    for keep in ("Farmers grow the fruit here.", "The system was designed in Austria.", "In 1802 Dong Nai became a province.",
                 "The statue weighs 200 pounds.", "Type/Specialty: Agricultural tourism", "Directions: Walk on."):
        assert keep in out
    lone = "Stop 1: X\n\nYou can buy it for $2 a bag."
    assert v.final_sweep(lone) == lone            # a paragraph is never emptied
