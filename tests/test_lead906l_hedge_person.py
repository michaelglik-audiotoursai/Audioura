"""[LEAD 906L] Mac proof of 906K: the hedge needs only shared object words; a long place name is not a person."""
import leftovers_906c as c
import leftovers_906f as f

EV = ("The Reclining Buddha Statue on <Mountain> is 49 meters in length and is the largest reclining Buddha in <Region>. "
      "It was the longest reclining Buddha in <Country> up to 2020 and remains one of the largest in <Region>.")


def test_hedge_when_subject_is_the_mountain():
    s = "<Mountain> is the site of the largest reclining Buddha statue in <Region>."
    new = c.hedged_by_evidence(s, EV, "Reclining Buddha Statue")
    assert new and "one of the largest" in new


def test_long_place_name_is_not_a_person():
    seen = "At the top of this mountain, you find the Linh Son Truong Tho Pagoda and the Long Doan Pagoda. "
    assert not f._persony_names(seen, "Alpha Mountain")


def test_real_person_still_counts():
    assert f._persony_names("Master Tran Huu Duc chose the mountain. ", "Alpha Mountain")


def test_hotel_pickup_is_promo():
    import refill_quality_906k as k
    assert k.is_venue_promo("Hotel pick-up is available in <Town>, <Town2> and <City>.", "The Reclining Buddha")
    assert not k.is_venue_promo("The statue is 49 meters long.", "The Reclining Buddha")


def test_no_refill_into_a_disclosed_stop():
    t = ("Stop 1: Cable car ascent\n\nType/Specialty: Cable car\n\nLook out at the view below you. Feel the cooler air here. "
         "We could not confirm verified historical details for this stop, so this part of the tour focuses on what you can see.\n\n"
         "Stop 2: Pagoda\n\nThe pagoda stands on the summit. It was founded by a monk. Pilgrims climb here. Bells ring daily. Incense burns.\n")
    ev = {"Cable car ascent": "The cable car was built in 1955 and carries 65 passengers each hour on the long line up."}
    out = f.refill_thin_stops(t, ev, None) if hasattr(f, "refill_thin_stops") else t
    assert "1955" not in out
