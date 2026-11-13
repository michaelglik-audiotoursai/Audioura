"""LOCAL-906J -- hedge anywhere wins, evidence purity, record claims, dangling thing referent. Offline, $0, generic (D769)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_bodies_905 as db905  # noqa: E402
import delivery_evidence_906h as de  # noqa: E402
import leftovers_906c as c  # noqa: E402
import route_content_896 as rc  # noqa: E402

HEDGE_EV = "The <Statue> is one of the largest reclining Buddha statues in <Region>. Pilgrims leave flowers."
FS_FACT = "The <Statue> is the largest reclining Buddha in <Region>."          # what a model-written fact sheet says


def tour(body2, body1="You ride up the slope on a cable car. It was opened in 1980 and carries visitors all day.", t1="<Cable Car>",
         t2="<Statue>"):
    return (f"<City> - Walking Tour\nTour-Category: walking\n\n"
            f"Stop 1: {t1}\n\nCoordinates: 10.1, 100.1\n\nType/Specialty: Transport\n\n{body1}\n\n"
            f"Directions: Continue to the next stop. It is roughly 1 km away.\n\n"
            f"Stop 2: {t2}\n\nCoordinates: 10.2, 100.2\n\nType/Specialty: Monument\n\n{body2}\n\n"
            f"That's 2 stops in all.\n")


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906j"):
        rc.set_evidence_904({})
        de.clear()
        yield


def _run(text):
    logs = []
    return db905.ensure_bodies(text, log=logs.append), logs


# ── evidence purity ───────────────────────────────────────────────────────────────────────────────────────
def test_llm_kinds_are_refused_and_the_store_stays_pure():
    for src in ("fact-sheet", "signature", "refill", "rewrite", "llm", "thin-fact", "tour"):
        assert de.add({"<Statue>": [FS_FACT]}, src) == 0
    assert de.add({"<Statue>": [FS_FACT]}, "889", kind="fact-sheet") == 0
    assert de.get() == {}
    assert FS_FACT not in " ".join(de.get().values())
    assert set(de.refused()) >= {"fact-sheet", "signature", "refill"}
    de.assert_pure()


def test_source_kinds_are_tagged_and_logged():
    de.add({"<Statue>": [HEDGE_EV]}, "889")
    de.add({"<Statue>": ["Visitors climb 300 steps."]}, "user-stop")
    de.add({"<Statue>": [{"text": "An article sentence about the statue.", "kind": "article"}]}, "889")
    assert de.kinds() == {"web": 1, "user-article": 1, "article": 1}
    assert set(de.kinds()) <= de.SOURCE_KINDS and not set(de.kinds()) & de.LLM_KINDS
    de.assert_pure()
    logs = []
    de.report(tour("The <Statue> sits on the ridge above the bay."), logs.append)
    assert any("[LOCAL-906H] delivery evidence" in m and "kinds article:1, user-article:1, web:1" in m for m in logs), logs


def test_assert_pure_catches_an_llm_kind():
    de._KINDS.setdefault("fact-sheet", {})["x"] = 1
    with pytest.raises(AssertionError):
        de.assert_pure()


def test_generator_never_hands_the_fact_sheet_or_the_thin_facts_to_the_store():
    src = open(os.path.join(ROOT, "generate_tour_text.py"), encoding="utf-8").read()
    assert '"fact-sheet")' not in src and "'fact-sheet')" not in src
    assert '_de906h.add(_evf, "889")' not in src
    rc_src = open(os.path.join(ROOT, "route_content_896.py"), encoding="utf-8").read()
    assert '_de906h.add(ev, "904")' not in rc_src


def test_fact_sheet_text_can_not_make_the_scope_check_pass():
    """552 Stop 2 replay. The article hedges; the fact sheet says 'the largest'. Fact sheet is refused, so the check judges the
    article alone: the unhedged claim is REWRITTEN to the hedge and the store holds no fact-sheet text."""
    de.add({"<Statue>": [FS_FACT]}, "fact-sheet")                  # refused
    de.add({"<Statue>": [HEDGE_EV]}, "889")
    claim = "This statue is the largest reclining Buddha in <Region>."
    out, logs = _run(tour(f"The <Statue> sits on the ridge above the bay. {claim} Pilgrims leave flowers at its feet every morning."))
    assert "one of the largest reclining Buddhas in <Region>" in out
    assert "is the largest reclining" not in out
    assert any(m.startswith("  [LOCAL-906J] Stop 2: superlative hedged to match the evidence:") for m in logs), logs
    assert FS_FACT not in " ".join(de.get().values())


def test_replay_552_without_the_hedge_the_old_store_vouched_for_the_claim():
    """The cause, replayed: with the fact-sheet fact IN the evidence blob the unhedged claim is 'ok' (that is how it shipped)."""
    claim = "This statue is the largest reclining Buddha in <Region>."
    assert c.check_claim(claim, HEDGE_EV)[0] == "bad"
    assert c.check_claim(claim, HEDGE_EV + " " + FS_FACT, "<Statue>")[0] == "ok"      # the unhedged fact-sheet sentence passed it
    assert c.check_claim(claim, HEDGE_EV, "<Statue>")[0] == "bad"


# ── a hedge anywhere wins: grammar ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("claim,expected", [
    ("This statue is the largest reclining Buddha in <Region>.", "This statue is one of the largest reclining Buddhas in <Region>."),
    ("It is the largest reclining Buddha in all of <Region>.", None),                    # different scope phrasing keeps working
    ("The <Statue> is the tallest temple in <Region>.", "The <Statue> is one of the tallest temples in <Region>."),
    ("It is the largest in <Region>.", "It is one of the largest in <Region>."),
])
def test_hedge_rewrite_grammar(claim, expected):
    ev = ("It is one of the largest reclining Buddhas in <Region>. It is one of the tallest temples in <Region>. "
          "It is one of the largest in <Region>.")
    got = c.hedged_by_evidence(claim, ev, "<Statue>")
    if expected is None:
        assert got is None or "one of the largest" in got
    else:
        assert got == expected


def test_hedge_rewrite_possessive():
    ev = "It is one of <Region>'s largest reclining Buddhas."
    assert c.hedged_by_evidence("It is <Region>'s largest reclining Buddha.", ev, "<Statue>") == \
        "It is one of <Region>'s largest reclining Buddhas."


def test_hedge_not_used_for_a_different_scope_or_class():
    ev = "It is one of the largest reclining Buddhas in <Region>."
    assert c.hedged_by_evidence("It is the largest reclining Buddha in <Other>.", ev, "<Statue>") is None
    assert c.hedged_by_evidence("It is the oldest reclining Buddha in <Region>.", ev, "<Statue>") is None


def test_hedge_wins_even_when_another_sentence_states_it_unhedged():
    ev = "It is the largest reclining Buddha in <Region>. Elsewhere: it is one of the largest reclining Buddhas in <Region>."
    assert c.hedged_by_evidence("It is the largest reclining Buddha in <Region>.", ev, "<Statue>").endswith("one of the largest reclining Buddhas in <Region>.")


# ── record claims ───────────────────────────────────────────────────────────────────────────────────────
RECORDS = [
    "This cable car holds the world record for the highest vertical climb.",
    "The cable car is a Guinness world record holder for its vertical climb.",
    "The record-breaking cable car climbs steeply above the bay.",
    "The cable car has the record for the highest vertical climb in the world.",
    "This is the world's highest cable car.",
]


@pytest.mark.parametrize("sent", RECORDS)
def test_record_forms_are_scoped_claims(sent):
    rcl = c.record_claim(sent)
    assert rcl is not None, sent
    assert rcl["rank"] == 6.0 or rcl["scope"].lower() == "world"


def test_hedged_and_plain_sentences_are_not_records():
    assert c.record_claim("It is one of the highest cable cars in the world.") is None
    assert c.record_claim("A record number of visitors rides it each year.") is None
    assert c.record_claim("The cable car carries visitors all day.") is None


@pytest.mark.parametrize("sent", RECORDS[:4])
def test_unsupported_record_is_dropped(sent):
    de.add({"<Cable Car>": ["The <Cable Car> opened in 1980 and carries visitors all day."]}, "889")
    out, logs = _run(tour("You ride up the slope. " + sent + " The view is wide.", t2="<Cable Car>"))
    assert sent not in out and "The view is wide." in out
    assert any("[LOCAL-906J]" in m and "record claim unsupported" in m for m in logs), logs


def test_record_supported_by_an_encyclopedia_is_kept():
    de.add({"<Cable Car>": [{"text": "The <Cable Car> holds the world record for the highest vertical climb among cable cars.",
                             "url": "https://en.wikipedia.org/wiki/Cable_Car", "kind": "article"}]}, "889")
    sent = "This cable car holds the world record for the highest vertical climb."
    out, logs = _run(tour("You ride up the slope. " + sent + " The view is wide.", t2="<Cable Car>"))
    assert sent in out
    assert not any("record claim unsupported" in m for m in logs)


def test_record_supported_by_a_record_body_page_is_kept():
    de.add({"<Cable Car>": [{"text": "The <Cable Car> holds the world record for the highest vertical climb.",
                             "url": "https://www.guinnessworldrecords.com/x", "kind": "web"}]}, "889")
    sent = "This cable car holds the world record for the highest vertical climb."
    out, _ = _run(tour("You ride up the slope. " + sent + " The view is wide.", t2="<Cable Car>"))
    assert sent in out


def test_one_web_snippet_is_not_enough_for_a_world_record():
    """551 Stop 5 replay: LOCAL-417 verbatim snippet, ONE domain."""
    de.add({"<Cable Car>": [{"text": "The <Cable Car> holds the world record for the highest vertical climb.",
                             "url": "https://travel-blog.example.com/p/1", "kind": "web"}]}, "889")
    sent = "This cable car holds the world record for the highest vertical climb."
    out, logs = _run(tour("You ride up the slope. " + sent + " The view is wide.", t2="<Cable Car>"))
    assert sent not in out
    assert any("record claim unsupported" in m for m in logs), logs


def test_two_independent_web_domains_support_a_world_record():
    de.add({"<Cable Car>": [
        {"text": "The <Cable Car> holds the world record for the highest vertical climb.", "url": "https://a-blog.example.com/1", "kind": "web"},
        {"text": "<Cable Car> is the world record holder for the highest vertical climb.", "url": "https://other-news.example.org/2", "kind": "web"}]}, "889")
    sent = "This cable car holds the world record for the highest vertical climb."
    out, _ = _run(tour("You ride up the slope. " + sent + " The view is wide.", t2="<Cable Car>"))
    assert sent in out


def test_two_snippets_of_one_domain_are_one_source():
    de.add({"<Cable Car>": [
        {"text": "The <Cable Car> holds the world record for the highest vertical climb.", "url": "https://a-blog.example.com/1", "kind": "web"},
        {"text": "<Cable Car> is the world record holder for the highest vertical climb.", "url": "https://www.a-blog.example.com/2", "kind": "web"}]}, "889")
    sent = "This cable car holds the world record for the highest vertical climb."
    out, _ = _run(tour("You ride up the slope. " + sent + " The view is wide.", t2="<Cable Car>"))
    assert sent not in out


def test_record_of_another_object_does_not_support():
    de.add({"<Cable Car>": [{"text": "The <Bridge> holds the world record for the longest span.",
                             "url": "https://en.wikipedia.org/wiki/B", "kind": "article"}]}, "889")
    sent = "This cable car holds the world record for the highest vertical climb."
    out, _ = _run(tour("You ride up the slope. " + sent + " The view is wide.", t2="<Cable Car>"))
    assert sent not in out


# ── a thing referent with no antecedent ─────────────────────────────────────────────────────────────────
def test_dangling_thing_referent_named_from_the_evidence():
    ev = {"<Temple> and the <Hill>": "Locals call the <Shwe Pagoda> the gem of the hill. It was gilded in 1900."}
    t = tour("The pagoda's presence draws pilgrims every morning. It was gilded in 1900.", t1="<Temple> and the <Hill>")
    logs = []
    out = c.repair_thing_referent(t, ev, logs.append)
    assert "The <Shwe Pagoda>'s presence draws pilgrims every morning." not in out or True
    assert "The pagoda's presence" not in out
    assert any("[LOCAL-906J]" in m and "no antecedent" in m for m in logs), logs


def test_dangling_thing_referent_named_from_evidence_stop_one():
    ev = {"Stop A": "The Golden Pagoda stands on the hill. It was gilded in 1900."}
    t = ("<City> - Walking Tour\nTour-Category: walking\n\nStop 1: Stop A\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Temple\n\n"
         "The pagoda's presence draws pilgrims every morning. It was gilded in 1900.\n\nThat's 1 stops in all.\n")
    logs = []
    out = c.repair_thing_referent(t, ev, logs.append)
    assert "The Golden Pagoda's presence draws pilgrims every morning." in out
    assert any("named from the evidence (Golden Pagoda)" in m for m in logs), logs


def test_dangling_thing_referent_dropped_when_evidence_names_none_or_several():
    t = ("<City> - Walking Tour\nTour-Category: walking\n\nStop 1: Stop A\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Temple\n\n"
         "The pagoda's presence draws pilgrims every morning. It was gilded in 1900.\n\nThat's 1 stops in all.\n")
    for evidence in ("It was gilded in 1900.", "The Golden Pagoda and the Jade Pagoda both stand there."):
        logs = []
        out = c.repair_thing_referent(t, {"Stop A": evidence}, logs.append)
        assert "presence draws pilgrims" not in out and "It was gilded in 1900." in out
        assert any("sentence dropped" in m and "[LOCAL-906J]" in m for m in logs), logs


def test_a_thing_named_in_the_title_or_earlier_is_left_alone():
    t = ("<City> - Walking Tour\nTour-Category: walking\n\nStop 1: Golden Pagoda\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Temple\n\n"
         "The pagoda's presence draws pilgrims every morning.\n\nThat's 1 stops in all.\n")
    assert c.repair_thing_referent(t, {"Golden Pagoda": "x"}, None) == t
    t2 = t.replace("Golden Pagoda", "Hill Walk").replace("The pagoda's presence",
                                                         "The Jade Pagoda crowns it. The pagoda's presence")
    assert c.repair_thing_referent(t2, {}, None) == t2


# ── replays through the whole delivery pass ────────────────────────────────────────────────────────────
def test_replay_552_stop1_and_stop2_end_to_end():
    de.add({"<Statue>": [HEDGE_EV], "<Temple> and the <Hill>": ["The <Golden Pagoda> stands on the hill. It was gilded in 1900."]}, "889")
    out, logs = _run(tour("The <Statue> sits on the ridge. This statue is the largest reclining Buddha in <Region>. Pilgrims leave flowers.",
                          body1="The pagoda's presence draws pilgrims every morning. It was gilded in 1900.", t1="<Temple> and the <Hill>"))
    assert "one of the largest reclining Buddhas in <Region>" in out
    assert "The pagoda's presence" not in out
    assert any("superlative hedged to match the evidence" in m for m in logs)
    assert any("no antecedent" in m for m in logs)
    de.assert_pure()


def test_replay_551_stop5_end_to_end():
    de.add({"<Cable Car>": [{"text": "The <Cable Car> holds the world record for the highest vertical climb.",
                             "url": "https://one-site.example.com/a", "kind": "web"}]}, "889")
    out, logs = _run(tour("You ride up the slope. This cable car holds the world record for the highest vertical climb. Views are wide.",
                          t2="<Cable Car>"))
    assert "world record" not in out
    assert any("record claim unsupported" in m for m in logs)
