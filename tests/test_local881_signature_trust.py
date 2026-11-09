"""LOCAL-881 — offline tests: the signature-story picker trusts only the stop's
OWN source, drops off-site location claims, rejects myths, checks relative time,
keeps the full date; the claim gate lets contradiction beat protection; and the
Wikipedia-evidence dense-centre gate rejects a different nearby building.

Every INPUT string below is from the ticket's "Tests (exact strings as INPUT
only)" section. No network: narrate_fn and fetch_fn are injected. Nothing is
hard-coded to the Saigon tour (D769) — the same detectors drive a control case.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import signature_story as ss
import landmark_claim_gate as lg
import landmark_wikipedia_evidence as we


# ──────────────────────────────────────────────────────────────────────────────
# 1. An Eiffel myth, with evidence that CORRECTS it: rejected, not protected.
# ──────────────────────────────────────────────────────────────────────────────
POST_OFFICE_OWN_EV = (
    "Saigon Central Post Office - Wikipedia (en). The Saigon Central Post Office "
    "was built between 1886 and 1891. It is often wrongly attributed to Gustave "
    "Eiffel, but was in fact designed by Alfred Foulhoux."
)


def _narrate_eiffel(system, user, model, **kw):
    return ({"stories": [{
        "story": "The post office was designed by the renowned French engineer "
                 "Gustave Eiffel.",
        "why_memorable": "famous person",
        "source_sentence": "It is often wrongly attributed to Gustave Eiffel, but "
                           "was in fact designed by Alfred Foulhoux.",
    }]}, 900, 80)


def test_eiffel_myth_story_is_rejected():
    stories, rep = ss.select_signature_stories(
        "Saigon Central Post Office", POST_OFFICE_OWN_EV,
        location="Ho Chi Minh City, Vietnam", narrate_fn=_narrate_eiffel,
        own_evidence_text=POST_OFFICE_OWN_EV, page_facts=[], aliases=[])
    assert stories == [], stories
    assert rep["dropped_myth"] >= 1


def test_eiffel_myth_is_not_protected_at_the_gate():
    # even if a story's source names Eiffel, a body sentence stating the myth as
    # fact must be dropped by the gate (contradiction beats protection).
    body = ("Orientation: Stand in the square. The post office was built in 1860 "
            "and the French engineer Gustave Eiffel played a role in its design. "
            "It was completed in 1891.")
    evid = [POST_OFFICE_OWN_EV]
    protected = ["It is often wrongly attributed to Gustave Eiffel, but was in "
                 "fact designed by Alfred Foulhoux."]
    new, removed = lg.filter_stop_body(
        body, evid, "Saigon Central Post Office",
        location="Ho Chi Minh City, Vietnam", protected=protected,
        authority_items=evid)
    assert "Eiffel" not in new or "wrongly" in new.lower(), new
    assert any("eiffel" in r["sentence"].lower() for r in removed), removed


# ──────────────────────────────────────────────────────────────────────────────
# 2. The Loan execution "right here" on a stop the evidence does not name:
#    dropped (or recast as city context).
# ──────────────────────────────────────────────────────────────────────────────
BOOK_STREET_OWN_EV = (
    "Nguyễn Văn Bình Book Street - Wikipedia (en). Nguyễn Văn Bình Book Street is "
    "a pedestrian book street in District 1, Ho Chi Minh City, opened in 2016 with "
    "over 20 bookstores."
)
LOAN_PAGE_FACT = {
    "text": "On 1 February 1968, Nguyễn Ngọc Loan executed a handcuffed Viet Cong "
            "prisoner, Nguyễn Văn Lém, on a Saigon street near the city center.",
    "url": "https://en.wikipedia.org/wiki/Nguyen_Ngoc_Loan",
}


def _narrate_loan(system, user, model, **kw):
    return ({"stories": [{
        "story": "On February 1, 1968, Nguyễn Ngọc Loan executed a handcuffed Viet "
                 "Cong prisoner, Nguyễn Văn Lém, right here on a Saigon street near "
                 "the city center.",
        "why_memorable": "conflict",
        "source_sentence": "On 1 February 1968, Nguyễn Ngọc Loan executed a "
                           "handcuffed Viet Cong prisoner, Nguyễn Văn Lém, on a "
                           "Saigon street near the city center.",
    }]}, 900, 90)


def test_loan_execution_right_here_is_dropped_on_unnamed_stop():
    stories, rep = ss.select_signature_stories(
        "Nguyễn Văn Bình Book Street", BOOK_STREET_OWN_EV + "\n" + LOAN_PAGE_FACT["text"],
        location="Ho Chi Minh City, Vietnam", narrate_fn=_narrate_loan,
        own_evidence_text=BOOK_STREET_OWN_EV, page_facts=[LOAN_PAGE_FACT],
        aliases=[])
    assert stories == [], stories
    # off-source OR location drop — the page fact does not name Book Street.
    assert rep["dropped_off_source"] + rep["dropped_location"] >= 1


def test_city_wide_event_told_as_context_passes_when_source_names_stop():
    # control: a true on-this-spot story whose source DOES name the stop is kept.
    ev = ("Independence Palace - Wikipedia (en). On 30 April 1975, a North "
          "Vietnamese tank crashed through the gates of the Independence Palace, "
          "ending the Vietnam War.")

    def _n(system, user, model, **kw):
        return ({"stories": [{
            "story": "On 30 April 1975 a tank crashed through the gates right here, "
                     "ending the war.",
            "why_memorable": "turning point",
            "source_sentence": "On 30 April 1975, a North Vietnamese tank crashed "
                               "through the gates of the Independence Palace, ending "
                               "the Vietnam War.",
        }]}, 900, 90)

    stories, rep = ss.select_signature_stories(
        "Independence Palace", ev, location="Ho Chi Minh City, Vietnam",
        narrate_fn=_n, own_evidence_text=ev, page_facts=[], aliases=[])
    assert len(stories) == 1, (stories, rep)


# ──────────────────────────────────────────────────────────────────────────────
# 3. A Gia Long Palace article for a "City Hall" stop pinned 600 m away: rejected.
# ──────────────────────────────────────────────────────────────────────────────
CITY_HALL_PIN = (10.7765, 106.7009)


def test_gia_long_palace_rejected_for_city_hall_600m_away():
    def fetch(name, lang):
        return {"pages": [{
            "title": "Gia Long Palace",
            "lead": "Gia Long Palace, now the Ho Chi Minh City Museum, was designed "
                    "by Alfred Foulhoux and completed in 1890.",
            "wikitext": "", "langlinks": [], "coord": (10.7760, 106.6954), "qid": ""}]}
    art = we.fetch_article("Ho Chi Minh City Hall", "en", fetch_fn=fetch,
                           use_cache=False, pin=CITY_HALL_PIN, city="Ho Chi Minh City")
    assert art is None, art


def test_city_hall_article_accepted_when_title_matches():
    def fetch(name, lang):
        return {"pages": [{
            "title": "Ho Chi Minh City Hall",
            "lead": "Ho Chi Minh City Hall was built between 1898 and 1909.",
            "wikitext": "", "langlinks": [], "coord": (10.7769, 106.7009), "qid": ""}]}
    art = we.fetch_article("Ho Chi Minh City Hall", "en", fetch_fn=fetch,
                           use_cache=False, pin=CITY_HALL_PIN, city="Ho Chi Minh City")
    assert art and art["title"] == "Ho Chi Minh City Hall", art


def test_bare_opera_house_name_still_accepted_within_2km():
    # a bare-name stop whose correct article is name-matched by containment and
    # sits at the complex centroid ~1.2 km away (>300 m) keeps the 2 km gate.
    opin = (10.7766, 106.7032)

    def fetch(name, lang):
        return {"pages": [{
            "title": "Saigon Opera House",
            "lead": "The Saigon Opera House opened in 1900.",
            "wikitext": "", "langlinks": [], "coord": (10.7855, 106.7050), "qid": ""}]}
    art = we.fetch_article("Opera House", "en", fetch_fn=fetch, use_cache=False,
                           pin=opin, city="Ho Chi Minh City")
    assert art and art["title"] == "Saigon Opera House", art


# ──────────────────────────────────────────────────────────────────────────────
# 4. "months before … 31 October 1966" with Nov 1963: dropped.
# ──────────────────────────────────────────────────────────────────────────────
def test_relative_time_months_with_three_year_gap_is_rejected_in_picker():
    ev = ("Independence Palace - Wikipedia (en). The palace was inaugurated on 31 "
          "October 1966. President Ngô Đình Diệm was assassinated in November 1963.")

    def _n(system, user, model, **kw):
        return ({"stories": [{
            "story": "In November 1963, Diệm was assassinated during a coup, months "
                     "before the palace's inauguration on 31 October 1966.",
            "why_memorable": "conflict",
            "source_sentence": "The palace was inaugurated on 31 October 1966.",
        }]}, 900, 90)

    stories, rep = ss.select_signature_stories(
        "Independence Palace", ev, location="Ho Chi Minh City, Vietnam",
        narrate_fn=_n, own_evidence_text=ev, page_facts=[], aliases=[])
    assert stories == [], (stories, rep)
    assert rep["dropped_rel_time"] >= 1


def test_relative_time_phrase_dropped_by_gate():
    body = ("Orientation: Approach the facade. In November 1963, Diệm was "
            "assassinated during a coup, months before the palace's inauguration "
            "on 31 October 1966.")
    evid = ["Independence Palace - Wikipedia (en). The palace was inaugurated on "
            "31 October 1966. Diệm was assassinated in November 1963."]
    protected = ["In November 1963, Diệm was assassinated during a coup, months "
                 "before the palace's inauguration on 31 October 1966."]
    new, removed = lg.filter_stop_body(
        body, evid, "Independence Palace", location="Ho Chi Minh City, Vietnam",
        protected=protected, authority_items=evid)
    assert "months before" not in new, new
    assert any(r["kind"] == "rel-time" for r in removed), removed


def test_relative_time_consistent_when_years_agree():
    assert ss.relative_time_consistent(
        "He died in 1963, three years before the 1966 inauguration.")
    assert not ss.relative_time_consistent(
        "He died in 1963, months before the 1966 inauguration.")


# ──────────────────────────────────────────────────────────────────────────────
# 5. The tank story keeps "30 April 1975".
# ──────────────────────────────────────────────────────────────────────────────
TANK_STORY = {
    "story": "A North Vietnamese tank crashed through the palace gates, ending the "
             "war.",
    "why_memorable": "turning point",
    "source_sentence": "On 30 April 1975, a North Vietnamese tank crashed through "
                       "the gates of the Independence Palace.",
    "source_date": {"day": 30, "month": 4, "year": 1975},
}


def test_body_without_date_fails_the_survival_check():
    body = ("A tank broke through the palace gates, now a powerful symbol of "
            "transition. He had fled in April.")
    gx = ss.derive_generic_tokens("Ho Chi Minh City, Vietnam", "Independence Palace")
    assert not ss.body_tells_story(body, TANK_STORY, generic_extra=gx)


def test_body_with_full_date_passes():
    body = ("On 30 April 1975, a North Vietnamese tank crashed through the palace "
            "gates — now a powerful symbol of transition.")
    gx = ss.derive_generic_tokens("Ho Chi Minh City, Vietnam", "Independence Palace")
    assert ss.body_tells_story(body, TANK_STORY, generic_extra=gx)


def test_source_date_is_attached_and_regen_prompt_carries_it():
    ev = ("Independence Palace - Wikipedia (en). On 30 April 1975, a North "
          "Vietnamese tank crashed through the gates of the Independence Palace.")

    def _n(system, user, model, **kw):
        return ({"stories": [{
            "story": "A North Vietnamese tank crashed through the gates on 30 April "
                     "1975, ending the war.",
            "why_memorable": "turning point",
            "source_sentence": "On 30 April 1975, a North Vietnamese tank crashed "
                               "through the gates of the Independence Palace.",
        }]}, 900, 90)

    stories, _ = ss.select_signature_stories(
        "Independence Palace", ev, location="Ho Chi Minh City, Vietnam",
        narrate_fn=_n, own_evidence_text=ev, page_facts=[], aliases=[])
    assert stories and stories[0].get("source_date") == {"day": 30, "month": 4, "year": 1975}
    block = ss.required_element_block(stories)
    assert "30 April 1975" in block

    captured = {}

    def _regen(system, user, model, **kw):
        captured["user"] = user
        return ({"sentences": [
            "On 30 April 1975, a North Vietnamese tank crashed through the gates.",
            "The moment ended the Vietnam War.",
            "The palace has stood as its witness ever since.",
            "You can still see the gates today.",
            "They remain a powerful symbol of transition."]}, 500, 120)

    sents, rep = ss.regenerate_body_with_story(
        "Independence Palace", "The palace stands quietly today.", stories,
        location="Ho Chi Minh City, Vietnam", narrate_fn=_regen)
    assert "30 April 1975" in captured["user"]
    assert sents and any("1975" in s for s in sents)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Control: a stop whose OWN article tells a true story still gets it, protected.
# ──────────────────────────────────────────────────────────────────────────────
OPERA_OWN_EV = (
    "Saigon Opera House - Wikipedia (en). During World War II, Allied forces bombed "
    "the Saigon Opera House in 1944, forcing its closure. The square outside is "
    "featured in Graham Greene's novel The Quiet American."
)


def _narrate_opera(system, user, model, **kw):
    return ({"stories": [{
        "story": "During World War II, Allied forces bombed the opera house in 1944.",
        "why_memorable": "conflict",
        "source_sentence": "During World War II, Allied forces bombed the Saigon "
                           "Opera House in 1944, forcing its closure.",
    }]}, 900, 90)


def test_true_own_source_story_is_kept_and_protected():
    stories, rep = ss.select_signature_stories(
        "Saigon Opera House", OPERA_OWN_EV, location="Ho Chi Minh City, Vietnam",
        narrate_fn=_narrate_opera, own_evidence_text=OPERA_OWN_EV, page_facts=[],
        aliases=[])
    assert len(stories) == 1, (stories, rep)
    # and the gate keeps a body sentence that tells it, protected.
    body = ("Orientation: Stand on the square. During the Second World War, Allied "
            "forces bombed the opera house in 1944, forcing it to close.")
    protected = [stories[0]["source_sentence"], stories[0]["story"]]
    new, removed = lg.filter_stop_body(
        body, [OPERA_OWN_EV], "Saigon Opera House",
        location="Ho Chi Minh City, Vietnam", protected=protected,
        authority_items=[OPERA_OWN_EV])
    assert "1944" in new and "bombed" in new.lower(), new


# ──────────────────────────────────────────────────────────────────────────────
# Generic / control (D769): the same detectors work for a non-Saigon tour.
# ──────────────────────────────────────────────────────────────────────────────
def test_detectors_are_generic_paris_control():
    # a myth about a Paris landmark is rejected the same way.
    ev = ("Eiffel Tower - Wikipedia (en). The Eiffel Tower is often wrongly said "
          "to have been Gustave Eiffel's sole design, but Maurice Koechlin drew the "
          "first sketches.")

    def _n(system, user, model, **kw):
        return ({"stories": [{
            "story": "The tower was Gustave Eiffel's sole design.",
            "why_memorable": "famous person",
            "source_sentence": "The Eiffel Tower is often wrongly said to have been "
                               "Gustave Eiffel's sole design, but Maurice Koechlin "
                               "drew the first sketches.",
        }]}, 900, 60)

    stories, rep = ss.select_signature_stories(
        "Eiffel Tower", ev, location="Paris, France", narrate_fn=_n,
        own_evidence_text=ev, page_facts=[], aliases=[])
    assert stories == [], (stories, rep)
    assert rep["dropped_myth"] >= 1


def test_distinctive_name_token_strips_city_and_kind_words():
    # "Ho Chi Minh City Hall" vs "Gia Long Palace" share no distinctive token
    # beyond city/kind words; but because the stop name has no distinctive token
    # of its own once city+kind words are removed, the token sub-condition is
    # vacuous (True) and the 300 m distance test is what rejects Gia Long Palace
    # (proven in test_gia_long_palace_rejected_for_city_hall_600m_away).
    assert we._titles_share_distinctive_token(
        "Ho Chi Minh City Hall", "Gia Long Palace", "Ho Chi Minh City")
    # a stop WITH a distinctive token: a title sharing it passes, one that does
    # not fails.
    assert we._titles_share_distinctive_token(
        "Bạch Đằng Pier", "Bạch Đằng Wharf", "Ho Chi Minh City")
    assert not we._titles_share_distinctive_token(
        "Bạch Đằng Pier", "Gia Long Palace", "Ho Chi Minh City")
