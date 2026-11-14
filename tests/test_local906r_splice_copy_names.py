"""[LOCAL-906R] Measure splice, day-trip / operator wording, passive restaurant plug, disclosure on a stop with facts, builder
spelling across tours, "This <noun>" antecedent, boundary list, cable car numbers from accepted evidence. $0, generic names (D769)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import leftovers_906c as c  # noqa: E402
import leftovers_906f as f  # noqa: E402
import route_content_896 as rc  # noqa: E402
import splice_copy_906r as sp  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906r"):
        yield


def stop(body, title="Alpha Mountain", ori="Here.", num=1):
    return (f"Stop {num}: {title}\n\nCoordinates: 1, 1\n\nOrientation: {ori}\n\n{body}\n\nDirections: Go.\n\n")


KEEP = "The mountain rises above the old town and the river."
KEEP2 = "A small shrine sits near the summit path."


# ── 1. splice ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", [
    "Among its most striking features is a reclining Buddha statue, stretching an impressive in length.",
    "The bridge has a total length of.",
    "The tower is measuring meters high.",
    "The wall is an impressive long.",
])
def test_broken_splice_never_delivered(x):
    logs = []
    out = sp.drop_splice(stop(f"{KEEP} {KEEP2} {x}"), logs.append)
    assert "impressive in length" not in out and "total length of." not in out and "measuring meters" not in out
    assert "impressive long." not in out
    assert KEEP in out and KEEP2 in out
    assert any("measure was removed without its phrase" in m for m in logs)


def test_number_removal_takes_its_clause_not_the_whole_sentence():
    x = "Among its most striking features is a reclining Buddha statue, stretching an impressive in length."
    out = sp.drop_splice(stop(f"{KEEP} {KEEP2} {x}"))
    assert "Among its most striking features is a reclining Buddha statue." in out


def test_whole_measure_sentence_is_kept():
    x = "The statue stretches an impressive 49 meters in length."
    assert x in sp.drop_splice(stop(f"{KEEP} {KEEP2} {x}"))


def test_thin_destination_stop_is_refilled(monkeypatch):
    x = "Among its most striking features is a reclining Buddha statue, stretching an impressive in length."
    ev = {"Alpha Mountain": ("Alpha Mountain is a mountain in Beta Province. The mountain was settled by farmers in the early 1900s and "
                             "grew around its temple. The summit temple holds an annual festival every spring. "
                             "A narrow road climbs the western slope to the summit gate.")}
    t = stop(x)
    out = sp.last_word(t, ev)
    assert "impressive in length" not in out
    assert len(f._stops(out)[0]["flat"]) >= 2


# ── 2. day-trip / operator copy ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", [
    "Many tours recommend visiting both the White Dunes and the Red Dunes during your trip.",
    "Another choice is a half-day private tour to Alpha Mountain.",
    "Drive for around 1.5 hours to Gamma Town, a coastal town known for its beaches and dunes.",
    "Visitors often combine this stop with the lighthouse down the coast.",
    "The full tour from Origin Town to Alpha Mountain, including the market, typically starts at 8:00 a.m. and lasts around eight hours.",
    "You can't visit Gamma Town without stopping to see the old harbor.",
    "It takes roughly one hour to drive by private car with air conditioning.",
])
def test_operator_copy_dropped_fact_kept(x):
    out = sp.run_pass(stop(f"{KEEP} {x} {KEEP2}"))
    assert x not in out and KEEP in out and KEEP2 in out


def test_drive_distance_between_stops_is_kept():
    x = "The next stop is about 45 kilometers away, roughly an hour's drive along the coast."
    assert x in sp.run_pass(stop(f"{KEEP} {x} {KEEP2}"))


def test_operator_tail_clause_is_cut_and_the_fact_stays():
    x = "The lighthouse is about 45 kilometers from the center, which takes roughly one hour to drive by private car with air conditioning."
    out = sp.run_pass(stop(f"{KEEP} {x} {KEEP2}"))
    assert "private car" not in out and "The lighthouse is about 45 kilometers from the center." in out


# ── 3. passive restaurant plug ────────────────────────────────────────────────────────────────────────────
PLUG = "Some of the best seafood in Gamma is served nearby at Blue Fin restaurant, right on the banks of the Long River."


def test_passive_restaurant_plug_dropped():
    out = sp.run_pass(stop(f"{KEEP} {PLUG} {KEEP2}"))
    assert PLUG not in out and KEEP in out


def test_stop_named_for_the_restaurant_keeps_it():
    t = stop(f"{KEEP} {PLUG} {KEEP2}", title="Blue Fin Restaurant")
    assert PLUG in sp.run_pass(t)


# ── 4. disclosure ─────────────────────────────────────────────────────────────────────────────────────────
DISC = ("We could not confirm verified historical details for this stop, so this part of the tour focuses on what you can see and "
        "sense here rather than on dates or events.")
LEAD = "Take a moment at Alpha Mountain and take in the place and the pace of the day."
LEAD2 = "Listen for the sounds that belong to this spot, and notice how the light falls around you."
EVID = {"Alpha Mountain": ("Alpha Mountain is an old volcanic mountain in Beta Province near the coast. The mountain was a place of "
                           "pilgrimage for farmers from the nearby villages. A small shrine sits near the summit path above the town. "
                           "The mountain rises above the old town and the river.")}


def test_disclosure_dropped_when_the_stop_has_two_supported_sentences():
    ori = ("Alpha Mountain is an old volcanic mountain in Beta Province near the coast. The mountain was a place of pilgrimage for "
           "farmers from the nearby villages. A small shrine sits near the summit path above the town.")
    logs = []
    out = sp.drop_disclosure_with_facts(stop(f"{LEAD} {LEAD2} {DISC}", ori=ori), EVID, logs.append)
    assert "could not confirm" not in out and "Take a moment at" not in out
    assert "old volcanic mountain" in out
    assert any("no-history disclosure" in m for m in logs)


def test_disclosure_kept_on_a_factless_stop():
    t = stop(f"{LEAD} {LEAD2} {DISC}", ori="Here.")
    assert "could not confirm" in sp.drop_disclosure_with_facts(t, EVID)
    assert "could not confirm" in sp.drop_disclosure_with_facts(t, {})


# ── 5. builder spelling ───────────────────────────────────────────────────────────────────────────────────
ART = "In 1958, Truong Dinh Tri began building the statue on the mountain. The statue was completed in 1963 by his students."


def test_article_spelling_wins_in_the_body():
    import delivery_evidence_906h as de
    de.add({"Alpha Mountain": ART}, "article")        # the stop's own encyclopedia article
    t = stop("In 1958 a man named Truong Dinh Y began building the statue. " + KEEP, ori="The statue is large and old.")
    logs = []
    out = sp.unify_with_article(t, {"Alpha Mountain": ART}, logs.append)
    assert any("builder spelling" in m for m in logs)
    assert "Truong Dinh Tri" in out and "Truong Dinh Y" not in out


def test_article_spelling_wins_in_the_signature_story():
    story, ch = sp.align_names("Truong Dinh Y started to carve the 49 meter-long statue.", ART)
    assert "Truong Dinh Tri started to carve" in story and ch == [("Truong Dinh Y", "Truong Dinh Tri")]


def test_signature_story_is_wired():
    assert "splice_copy_906r" in open(os.path.join(ROOT, "signature_story.py"), encoding="utf-8").read()


def test_a_name_the_article_spells_the_same_way_is_not_touched():
    story, ch = sp.align_names("Truong Dinh Tri began building the statue.", ART)
    assert ch == [] and "Truong Dinh Tri" in story


# ── 6. "This statue" with no antecedent ───────────────────────────────────────────────────────────────────
def test_this_statue_without_antecedent_is_dropped_or_named():
    x = "This statue is considered the pride of Alpha Mountain and draws many visitors."
    t = stop(f"At the summit you will find two sacred pagodas. {x} {KEEP}", title="Arriving at Alpha Mountain")
    out = c.repair_thing_referent(t, {"Arriving at Alpha Mountain": "A mountain in Beta Province."})
    assert "This statue is considered" not in out and KEEP in out
    named = c.repair_thing_referent(t, {"Arriving at Alpha Mountain": "The Lotus Statue stands on the summit."})
    assert "This statue" not in named and "Lotus Statue" in named


def test_this_statue_with_antecedent_is_kept():
    x = "This statue is considered the pride of Alpha Mountain."
    t = stop(f"A large statue stands on the summit. {x} {KEEP}", title="Arriving at Alpha Mountain")
    assert x in c.repair_thing_referent(t, {"Arriving at Alpha Mountain": "A mountain."})


# ── 7. boundary list ──────────────────────────────────────────────────────────────────────────────────────
def test_geography_boundary_sentence_dropped():
    x = ("Geographically, Alpha ward lies with the South Sea to the east and south, Beta ward and Gamma commune to the west, "
         "and Delta commune and Epsilon district to the north.")
    ori = f"Alpha is a coastal ward. {x} Since the 1990s it became a resort."
    out = sp.drop_boundary(stop(KEEP, ori=ori))
    assert "Geographically" not in out and "coastal ward" in out and "resort" in out


def test_a_plain_direction_sentence_is_not_a_boundary_list():
    x = "The shrine lies to the north of the lake and the road runs to the east."
    assert x in sp.drop_boundary(stop(f"{KEEP} {x}"))


# ── 8. cable car number ───────────────────────────────────────────────────────────────────────────────────
CABLE = "The cable car route is 7,455 meters long and carries visitors to the summit."
CEV = {"Alpha Cable Car": ("The cable car carries visitors to the summit in about fifteen minutes. The cable car route is 7,455 meters "
                           "long and is one of the longest in the region ...")}


def test_number_only_in_a_rejected_snippet_is_not_delivered():
    t = stop(f"{CABLE} {KEEP} {KEEP2}", title="Alpha Cable Car")
    logs = []
    out = sp.cable_car_accepted_numbers(t, CEV, logs.append)
    assert "7,455" not in out and KEEP in out
    assert any("refused snippet" in m for m in logs)


def test_number_in_an_accepted_passage_is_kept_and_logged():
    ev = {"Alpha Cable Car": "The cable car route is 7,455 meters long and carries visitors to the summit station."}
    t = stop(f"{CABLE} {KEEP} {KEEP2}", title="Alpha Cable Car")
    logs = []
    out = sp.cable_car_accepted_numbers(t, ev, logs.append)
    assert "7,455" in out and any("kept" in m for m in logs)


# ── wiring ────────────────────────────────────────────────────────────────────────────────────────────────
def test_wired():
    assert "splice_copy_906r" in open(os.path.join(ROOT, "leftovers_906f.py"), encoding="utf-8").read()
    assert "splice_copy_906r" in open(os.path.join(ROOT, "delivery_bodies_905.py"), encoding="utf-8").read()


def test_run_pass_is_idempotent_and_never_raises():
    t = stop(f"{KEEP} {PLUG} {KEEP2}")
    once = sp.run_pass(t, EVID)
    assert sp.run_pass(once, EVID) == once
    assert sp.run_pass("", None) == ""
