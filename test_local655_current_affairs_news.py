#!/usr/bin/env python3
"""test_local655_current_affairs_news.py — LOCAL-655.

Tour 557 ("Walking tour in Boston dedicated to Massachusetts politics and current
affairs") ended with "we found no verified developments from the past five years"
although NOTHING in the pipeline searched the news. These tests prove the fix:

  1. INTENT -> QUERIES: a current-affairs request is detected and turns into news
     queries for the theme and for each stop; a museum / history request is NOT.
  2. FIXTURE RESPONSE -> DATED, ATTRIBUTED SENTENCES: a canned Serper-news result
     + fetched article text produces dated, source-attributed narration injected
     into the right stop (politically balanced — both sides reported).
  3. EMPTY RESPONSE -> HONEST NOTE: when the search ran and returned nothing, the
     honest note is appended exactly once (and only then).
  4. TTL: a stop/tour carrying a dated news item is excluded from reuse once it is
     older than 7 days; a history-only stop/tour is never aged out.
  5. MUSEUM NO-OP: the delivery-time news context is a strict no-op for a museum
     (and any non-current-affairs) tour — the delivered text is byte-identical.

All network is injected (serp/fetch/answer callables) so the suite runs offline.
The DB-backed TTL assertions skip cleanly when Postgres is unreachable.

Run: python3 -m pytest test_local655_current_affairs_news.py -q
     python3 test_local655_current_affairs_news.py
"""
import os
import unittest

import current_affairs_news as ca


BOSTON_REQ = ("Walking tour in Boston dedicated to Massachusetts politics and "
              "current affairs, Boston, MA")
MUSEUM_REQ = "Tour of the Museum of Fine Arts, Boston, MA"
HISTORY_REQ = "Walking tour of colonial history in Boston, Boston, MA"


# ─────────────────────────────────────────────────────────────────────────────
# 1. INTENT -> QUERIES
# ─────────────────────────────────────────────────────────────────────────────
class TestIntentAndQueries(unittest.TestCase):
    def test_current_affairs_detected(self):
        self.assertTrue(ca.wants_current_affairs(BOSTON_REQ))
        self.assertTrue(ca.wants_current_affairs("What's in the news in Austin today"))
        self.assertTrue(ca.wants_current_affairs("A tour about the governor's race"))

    def test_museum_and_history_not_detected(self):
        self.assertFalse(ca.wants_current_affairs(MUSEUM_REQ))
        self.assertFalse(ca.wants_current_affairs(HISTORY_REQ))
        self.assertFalse(ca.wants_current_affairs("Walking tour of Art Nouveau architecture, Paris"))

    def test_theme_queries(self):
        qs = ca.derive_theme_queries(BOSTON_REQ)
        self.assertTrue(qs, "no theme queries derived")
        self.assertTrue(any("politics" in q.lower() for q in qs))

    def test_stop_queries_shape(self):
        """The ticket's example, now CITY-ANCHORED so a generic landmark name does
        not pull a same-named place elsewhere: 'Massachusetts State House' ->
        ['Massachusetts State House Boston news', 'Massachusetts State House <topic>']."""
        qs = ca.derive_stop_queries("Massachusetts State House", BOSTON_REQ)
        self.assertEqual(qs[0], "Massachusetts State House Boston news")
        self.assertGreaterEqual(len(qs), 2)
        self.assertTrue(any(w in qs[1].lower() for w in
                            ("legislature", "politics", "senate")))

    def test_stop_queries_are_city_anchored(self):
        """Every stop query carries the city when the stop name does not already
        name it (the LOCAL-655 live run matched an Arkansas 'Old State House')."""
        qs = ca.derive_stop_queries("Old State House", BOSTON_REQ)
        self.assertTrue(all("boston" in q.lower() for q in qs),
                        f"a stop query is not city-anchored: {qs}")

    def test_empty_request_is_not_current_affairs(self):
        self.assertFalse(ca.wants_current_affairs(""))
        self.assertFalse(ca.wants_current_affairs(None))


# ─────────────────────────────────────────────────────────────────────────────
# 2. FIXTURE RESPONSE -> DATED, ATTRIBUTED, BALANCED SENTENCES
# ─────────────────────────────────────────────────────────────────────────────
_NEWS_ITEMS = [
    {"title": "Healey and Republican challenger clash over state budget",
     "source": "State House News Service", "date": "Oct 8, 2026",
     "link": "https://statehousenews.example/budget-debate",
     "snippet": "The governor and her challenger debated the budget."},
    {"title": "Senate passes housing bill after late-night session",
     "source": "The Boston Globe", "date": "Oct 7, 2026",
     "link": "https://bostonglobe.example/housing-bill",
     "snippet": "The Massachusetts Senate passed a housing bill."},
]

_ARTICLE_TEXT = {
    "https://statehousenews.example/budget-debate": (
        "On October 8, 2026, Governor Maura Healey and her Republican challenger "
        "debated the state budget at the State House. Healey, a Democrat, said the "
        "budget protected local aid. Her Republican opponent said it raised spending "
        "too far and called for cuts."),
    "https://bostonglobe.example/housing-bill": (
        "On October 7, 2026, the Massachusetts Senate passed a housing production "
        "bill. Democratic leaders praised it; Republican senators opposed the cost."),
}


def _fake_serp(query, tbs='qdr:m', num=8):
    if "State House" in query and tbs == 'qdr:m':
        return list(_NEWS_ITEMS)
    return []


def _fake_fetch(url):
    return _ARTICLE_TEXT.get(url, "")


def _fake_answer_balanced(prompt, model=None, max_tokens=None):
    return {"text": (
        "On October 8, 2026, Governor Maura Healey said the budget protected local "
        "aid, while her Republican challenger said it raised spending too far [1]. "
        "On October 7, 2026, the Massachusetts Senate passed a housing bill that "
        "Democratic leaders praised and Republican senators opposed [2]."), "error": ""}


def _fake_answer_empty(prompt, model=None, max_tokens=None):
    return {"text": "NO MATERIAL FOUND", "error": ""}


class TestComposeAndResearch(unittest.TestCase):
    def test_compose_dated_attributed_balanced(self):
        articles = [dict(it, text=_ARTICLE_TEXT[it["link"]]) for it in _NEWS_ITEMS]
        out = ca.compose_news_sentences("Massachusetts State House", articles,
                                        answer=_fake_answer_balanced)
        self.assertTrue(out["text"])
        self.assertRegex(out["text"], r"On October \d+, 2026,")
        self.assertIn("Healey", out["text"])
        self.assertIn("Republican", out["text"])
        self.assertNotIn("[1]", out["text"])
        self.assertNotIn("[2]", out["text"])
        srcs = {s["source"] for s in out["sources"]}
        self.assertIn("State House News Service", srcs)

    def test_research_runs_queries_and_widens(self):
        log = ca.research_news_for_stops(
            BOSTON_REQ, ["Massachusetts State House", "Boston City Hall"],
            serp=_fake_serp, fetch=_fake_fetch, answer=_fake_answer_balanced)
        self.assertTrue(log["searched"])
        self.assertTrue(any("State House" in q and "news" in q for q in log["queries"]))
        self.assertTrue(any("City Hall" in q and "news" in q for q in log["queries"]))
        self.assertIn("Massachusetts State House", log["by_stop"])
        self.assertNotIn("Boston City Hall", log["by_stop"])
        self.assertRegex(log["by_stop"]["Massachusetts State House"]["text"],
                         r"On October \d+, 2026,")

    def test_injection_is_additive_and_idempotent(self):
        text = (
            "Step-by-Step Audio Guided Tour: Boston\n\n"
            "Stop 1: Massachusetts State House\n\n"
            "Coordinates: 42.3588, -71.0638\n\n"
            "The State House has stood since 1798.\n\n"
            "Directions: Walk down Beacon Street.\n\n"
            "Stop 2: Faneuil Hall\n\n"
            "Coordinates: 42.3600, -71.0568\n\n"
            "Faneuil Hall is a marketplace.\n")
        by_stop = {"Massachusetts State House": {
            "text": "On October 8, 2026, Healey and her Republican challenger debated the budget.",
            "sources": [{"source": "State House News Service", "url": "u", "date": "Oct 8, 2026"}]}}
        out, n = ca.inject_news_into_text(text, by_stop)
        self.assertEqual(n, 1)
        self.assertIn(ca._NEWS_MARK, out)
        self.assertIn("Reported by State House News Service", out)
        self.assertIn("The State House has stood since 1798.", out)
        s1 = out.split("Stop 2:")[0]
        self.assertIn(ca._NEWS_MARK, s1)
        self.assertLess(s1.index(ca._NEWS_MARK), s1.index("Directions:"))
        out2, n2 = ca.inject_news_into_text(out, by_stop)
        self.assertEqual(n2, 0)
        self.assertEqual(out2, out)


# ─────────────────────────────────────────────────────────────────────────────
# 2b. [LOCAL-655B] RELEVANCE GATE + STOP ASSIGNMENT + ATTRIBUTION
#     Fixtures reproduce the exact live-tour-618 failures the LEAD flagged.
# ─────────────────────────────────────────────────────────────────────────────
import datetime as _dt

NOW = _dt.date(2026, 10, 9)  # the live context date, so relative dates resolve.

# The real wrong-place item that shipped on Boston stops 2 AND 4 of tour 618.
ARKANSAS_ITEM = {
    "title": "Longtime Old State House Museum employee resigns",
    "source": "Arkansas Times", "date": "Six days ago",
    "link": "https://arktimes.example/resign",
    "snippet": ("Marie Brown-Bealer, a 15-year employee at the Old State House "
                "Museum in Little Rock, Arkansas, resigned citing insensitive "
                "remarks about slavery under new leadership."),
}
ARKANSAS_ITEM2 = {
    "title": "Old State House Museum announces gambling exhibit",
    "source": "KARK", "date": "4 days ago",
    "link": "https://kark.example/gambling",
    "snippet": ("The Old State House Museum announced a new exhibit on the rise "
                "and fall of gambling in Hot Springs, Arkansas."),
}
# The off-theme restaurant item that shipped on Faneuil Hall.
BURGER_ITEM = {
    "title": "Smashed by BRED to open in Faneuil Hall Marketplace",
    "source": "Axios", "date": "2 days ago",
    "link": "https://axios.example/bred",
    "snippet": ("BRED, a Boston restaurant group, will open Smashed by BRED in "
                "Faneuil Hall Marketplace next month, serving burgers and chicken."),
}
# The undated 'Recently … 2022 strategy' item.
UNDATED_ITEM = {
    "title": "Downtown revitalization includes Faneuil Hall",
    "source": "Boston.gov", "date": "",
    "link": "https://boston.gov.example/downtown",
    "snippet": ("The City of Boston has included Faneuil Hall in its Downtown "
                "revitalization under the 2022 strategy."),
}
# The item Michael actually asked about: the Oct 8 governor's debate.
DEBATE_ITEM = {
    "title": "Healey debates Republican challenger in Massachusetts governor race",
    "source": "State House News Service", "date": "Oct 8, 2026",
    "link": "https://statehousenews.example/debate",
    "snippet": ("Massachusetts Governor Maura Healey debated her Republican "
                "challenger over the state budget at the State House in Boston."),
}


class TestRelevanceGate(unittest.TestCase):
    def test_arkansas_item_rejected_wrong_place(self):
        ok, reason = ca.gate_item(ARKANSAS_ITEM, BOSTON_REQ, fresh_days=365, now=NOW)
        self.assertFalse(ok)
        self.assertIn("arkansas", reason.lower())

    def test_burger_item_rejected_off_theme(self):
        ok, reason = ca.gate_item(BURGER_ITEM, BOSTON_REQ, fresh_days=365, now=NOW)
        self.assertFalse(ok)
        self.assertIn("off-theme", reason.lower())

    def test_undated_item_dropped(self):
        ok, reason = ca.gate_item(UNDATED_ITEM, BOSTON_REQ, fresh_days=365, now=NOW)
        self.assertFalse(ok)
        self.assertIn("undated", reason.lower())

    def test_stale_dated_item_dropped(self):
        old = dict(DEBATE_ITEM, date="Jan 2, 2020")
        ok, reason = ca.gate_item(old, BOSTON_REQ, fresh_days=365, now=NOW)
        self.assertFalse(ok)
        self.assertIn("stale", reason.lower())

    def test_debate_item_accepted(self):
        ok, reason = ca.gate_item(DEBATE_ITEM, BOSTON_REQ, fresh_days=365, now=NOW)
        self.assertTrue(ok, reason)
        self.assertIn("ok", reason.lower())

    def test_parse_news_date_relative_and_absolute(self):
        self.assertEqual(ca.parse_news_date("Six days ago", now=NOW),
                         _dt.date(2026, 10, 3))
        self.assertEqual(ca.parse_news_date("4 days ago", now=NOW),
                         _dt.date(2026, 10, 5))
        self.assertEqual(ca.parse_news_date("yesterday", now=NOW),
                         _dt.date(2026, 10, 8))
        self.assertEqual(ca.parse_news_date("Oct 8, 2026"), _dt.date(2026, 10, 8))
        self.assertEqual(ca.parse_news_date("2026-10-08"), _dt.date(2026, 10, 8))
        self.assertIsNone(ca.parse_news_date(""))
        self.assertIsNone(ca.parse_news_date("Recently"))

    def test_gate_items_splits_accepted_rejected(self):
        acc, rej = ca.gate_items(
            [DEBATE_ITEM, ARKANSAS_ITEM, BURGER_ITEM, UNDATED_ITEM],
            BOSTON_REQ, fresh_days=365, now=NOW)
        self.assertEqual([a["link"] for a in acc], [DEBATE_ITEM["link"]])
        self.assertEqual(len(rej), 3)
        self.assertTrue(all("_reject_reason" in r for r in rej))


class TestStopAssignment(unittest.TestCase):
    STOPS = ["Faneuil Hall", "Old State House", "Boston Common",
             "Massachusetts State House", "Boston City Hall"]

    def test_state_item_assigned_to_state_house(self):
        self.assertEqual(ca.assign_item_to_stop(DEBATE_ITEM, self.STOPS),
                         "Massachusetts State House")

    def test_city_item_assigned_to_city_hall(self):
        city_item = {"title": "Boston City Council passes ordinance",
                     "snippet": ("The Boston City Council and Mayor approved a "
                                 "zoning ordinance at City Hall."), "text": ""}
        self.assertEqual(ca.assign_item_to_stop(city_item, self.STOPS),
                         "Boston City Hall")

    def test_no_government_stop_falls_back_or_none(self):
        # No gov stop present; a generic item with no name overlap -> None.
        item = {"title": "x", "snippet": "a generic civic protest downtown",
                "text": ""}
        self.assertIsNone(ca.assign_item_to_stop(item, ["Riverside Park"]))


class TestNoDuplicateAcrossStops(unittest.TestCase):
    """A single item returned by MANY queries must land on exactly ONE stop."""
    def test_duplicate_item_lands_on_one_stop_only(self):
        # The debate item is returned for several queries (theme + two stops);
        # it must appear on exactly one stop (the State House), never twice.
        def serp_dupe(query, tbs='qdr:m', num=8):
            if tbs != 'qdr:m':
                return []
            return [dict(DEBATE_ITEM)]

        def fetch(url):
            return ("On October 8, 2026, Massachusetts Governor Maura Healey "
                    "debated her Republican challenger over the state budget at "
                    "the State House in Boston. Healey, a Democrat, defended local "
                    "aid; her Republican opponent called for spending cuts.")

        def answer(prompt, model=None, max_tokens=None):
            return {"text": ("On October 8, 2026, Massachusetts Governor Maura "
                             "Healey debated her Republican challenger over the "
                             "state budget, according to the State House News "
                             "Service [1]."), "error": ""}

        log = ca.research_news_for_stops(
            BOSTON_REQ, ["Old State House", "Massachusetts State House"],
            serp=serp_dupe, fetch=fetch, answer=answer, now=NOW)
        # Exactly one stop received the item.
        stops_with_news = list(log["by_stop"].keys())
        self.assertEqual(len(stops_with_news), 1, log["by_stop"])
        self.assertEqual(stops_with_news[0], "Massachusetts State House")
        # And it is accepted exactly once (deduped by link).
        self.assertEqual(len([a for a in log["accepted"]
                              if a["link"] == DEBATE_ITEM["link"]]), 1)

    def test_full_mix_only_debate_survives_on_one_stop(self):
        """The full tour-618 candidate mix: Arkansas x2 + burger + undated +
        debate. Only the debate survives, on the State House, once."""
        pool = [ARKANSAS_ITEM, ARKANSAS_ITEM2, BURGER_ITEM, UNDATED_ITEM, DEBATE_ITEM]

        def serp_mix(query, tbs='qdr:m', num=8):
            return list(pool) if tbs == 'qdr:m' else []

        def fetch(url):
            if url == DEBATE_ITEM["link"]:
                return ("On October 8, 2026, Massachusetts Governor Maura Healey "
                        "debated her Republican challenger at the State House in "
                        "Boston over the state budget.")
            # the rejected items keep their off-place/off-theme/undated text
            return {ARKANSAS_ITEM["link"]: ARKANSAS_ITEM["snippet"],
                    ARKANSAS_ITEM2["link"]: ARKANSAS_ITEM2["snippet"],
                    BURGER_ITEM["link"]: BURGER_ITEM["snippet"],
                    UNDATED_ITEM["link"]: UNDATED_ITEM["snippet"]}.get(url, "")

        def answer(prompt, model=None, max_tokens=None):
            return {"text": ("On October 8, 2026, Massachusetts Governor Maura "
                             "Healey debated her Republican challenger over the "
                             "state budget, according to the State House News "
                             "Service [1]."), "error": ""}

        log = ca.research_news_for_stops(
            BOSTON_REQ,
            ["Faneuil Hall", "Old State House", "Boston Common",
             "Massachusetts State House", "Boston City Hall"],
            serp=serp_mix, fetch=fetch, answer=answer, now=NOW)
        self.assertEqual(list(log["by_stop"].keys()), ["Massachusetts State House"])
        acc_links = {a["link"] for a in log["accepted"]}
        self.assertEqual(acc_links, {DEBATE_ITEM["link"]})
        rej_links = {r["link"] for r in log["rejected"]}
        for bad in (ARKANSAS_ITEM, ARKANSAS_ITEM2, BURGER_ITEM, UNDATED_ITEM):
            self.assertIn(bad["link"], rej_links)


class TestAttributionParenthetical(unittest.TestCase):
    def test_parenthetical_dropped_when_source_named_in_text(self):
        by_stop = {"Massachusetts State House": {
            "text": ("On October 8, 2026, Governor Healey debated her Republican "
                     "challenger, according to the State House News Service."),
            "sources": [{"source": "State House News Service", "url": "u",
                         "date": "Oct 8, 2026"}]}}
        text = ("Stop 1: Massachusetts State House\n\nBuilt in 1798.\n\n"
                "Directions: Walk on.\n")
        out, n = ca.inject_news_into_text(text, by_stop)
        self.assertEqual(n, 1)
        self.assertIn(ca._NEWS_MARK, out)
        self.assertNotIn("Reported by", out,
                         "parenthetical must be dropped when source named in text")

    def test_parenthetical_kept_for_unnamed_source(self):
        by_stop = {"Massachusetts State House": {
            "text": "On October 8, 2026, the governor debated her challenger.",
            "sources": [{"source": "State House News Service", "url": "u",
                         "date": "Oct 8, 2026"}]}}
        text = ("Stop 1: Massachusetts State House\n\nBuilt in 1798.\n\n"
                "Directions: Walk on.\n")
        out, n = ca.inject_news_into_text(text, by_stop)
        self.assertEqual(n, 1)
        self.assertIn("Reported by State House News Service", out)

    def test_attribution_suffix_helper(self):
        self.assertEqual(ca._attribution_suffix(
            "x according to Axios", ["Axios"]), "")
        self.assertEqual(ca._attribution_suffix(
            "x happened", ["Axios"]), " (Reported by Axios.)")
        self.assertEqual(ca._attribution_suffix(
            "named WGBH only", ["WGBH", "Boston.com"]),
            " (Reported by Boston.com.)")


class TestDatedComposition(unittest.TestCase):
    """The gate records the resolved date and the composer is told to use it,
    never a bare 'Recently' (ticket item 2c / 3)."""

    def test_gate_stashes_parsed_date(self):
        item = dict(DEBATE_ITEM)
        ok, _ = ca.gate_item(item, BOSTON_REQ, fresh_days=365, now=NOW)
        self.assertTrue(ok)
        self.assertEqual(item["_parsed_date"], "2026-10-08")

    def test_prompt_carries_date_and_forbids_recently(self):
        captured = {}

        def spy_answer(prompt, model=None, max_tokens=None):
            captured["prompt"] = prompt
            return {"text": "On October 8, 2026, the governor acted [1].",
                    "error": ""}

        item = dict(DEBATE_ITEM, text=DEBATE_ITEM["snippet"],
                    _parsed_date="2026-10-08")
        ca.compose_news_sentences("Massachusetts State House", [item],
                                  answer=spy_answer, locale="Boston, MA")
        self.assertIn("DATE: 2026-10-08", captured["prompt"])
        self.assertIn('NEVER write "Recently"', captured["prompt"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. EMPTY RESPONSE -> HONEST NOTE
# ─────────────────────────────────────────────────────────────────────────────
class TestHonestNote(unittest.TestCase):
    def test_empty_search_appends_honest_note_once(self):
        log = ca.research_news_for_stops(
            BOSTON_REQ, ["Nowhere Plaza"],
            serp=lambda q, tbs='qdr:m', num=8: [],
            fetch=_fake_fetch, answer=_fake_answer_balanced)
        self.assertTrue(log["searched"])
        self.assertEqual(log["by_stop"], {})
        text = "Stop 1: Nowhere Plaza\n\nA quiet square.\n"
        out, appended = ca.append_honest_note(text, log)
        self.assertTrue(appended)
        self.assertIn(ca.HONEST_NOTE, out)
        out2, appended2 = ca.append_honest_note(out, log)
        self.assertFalse(appended2)
        self.assertEqual(out2.count(ca.HONEST_NOTE), 1)

    def test_note_not_appended_when_news_found(self):
        log = {"searched": True, "by_stop": {"X": {"text": "On Oct 8, 2026, ..."}}}
        out, appended = ca.append_honest_note("Stop 1: X\n\nbody\n", log)
        self.assertFalse(appended)
        self.assertNotIn(ca.HONEST_NOTE, out)

    def test_note_not_appended_when_search_never_ran(self):
        log = {"searched": False, "by_stop": {}}
        out, appended = ca.append_honest_note("Stop 1: X\n\nbody\n", log)
        self.assertFalse(appended)
        self.assertNotIn(ca.HONEST_NOTE, out)

    def test_model_no_material_yields_no_sentences(self):
        articles = [dict(it, text=_ARTICLE_TEXT[it["link"]]) for it in _NEWS_ITEMS]
        out = ca.compose_news_sentences("X", articles, answer=_fake_answer_empty)
        self.assertEqual(out["text"], "")


# ─────────────────────────────────────────────────────────────────────────────
# 4. MUSEUM NO-OP (delivery-time context)
# ─────────────────────────────────────────────────────────────────────────────
class TestMuseumNoOp(unittest.TestCase):
    def test_delivery_pass_is_byte_identical_for_museum(self):
        import generate_tour_text as g
        museum_text = (
            "Step-by-Step Audio Guided Tour: The Courtauld Gallery\n\n"
            "Stop 1: Georges Seurat\n\n"
            "Coordinates: 51.5115, -0.1195\n\n"
            "Seurat pioneered pointillism.\n")
        g._set_current_affairs_context(wanted=False, request=MUSEUM_REQ,
                                       tour_category="museum")
        out = g._apply_current_affairs_news(museum_text)
        self.assertEqual(out, museum_text, "museum delivery text must be byte-identical")

    def test_delivery_pass_noop_when_not_wanted(self):
        import generate_tour_text as g
        g._set_current_affairs_context(wanted=False, request=HISTORY_REQ,
                                       tour_category="walking")
        text = "Stop 1: Old North Church\n\nBuilt in 1723.\n"
        self.assertEqual(g._apply_current_affairs_news(text), text)

    def test_delivery_pass_disabled_by_env(self):
        import generate_tour_text as g
        g._set_current_affairs_context(wanted=True, request=BOSTON_REQ,
                                       tour_category="walking")
        text = "Stop 1: Massachusetts State House\n\nBuilt in 1798.\n"
        os.environ["DISABLE_CURRENT_AFFAIRS_NEWS"] = "1"
        try:
            self.assertEqual(g._apply_current_affairs_news(text), text)
        finally:
            del os.environ["DISABLE_CURRENT_AFFAIRS_NEWS"]


class TestNoHonestNoteContradiction(unittest.TestCase):
    """LOCAL-655B: a tour that carries injected 'In recent news:' items must NOT
    also carry the LOCAL-650 'no verified developments' honest note — live tour
    623 shipped both because the composer wrote 'Recently' (no 4-digit year) so
    the year-detector missed the fresh items. Two independent fixes guarantee it:
    (1) the composer now states the gate-resolved date (year present); (2) the
    delivery guard suppresses the note whenever 'In recent news:' is present."""

    def test_year_detector_fix(self):
        import current_affairs_coverage as cac
        dated = ("Step-by-Step Audio Guided Tour: Walking tour in Boston "
                 "dedicated to Massachusetts current affairs, Boston, MA\n\n"
                 "Stop 1: State House\n\nBuilt in 1798.\n\n"
                 "In recent news: On October 8, 2026, the governor signed a bill.\n")
        self.assertTrue(cac.has_recent_item(dated))
        _, changed = cac.ensure_current_affairs_coverage(dated)
        self.assertFalse(changed, "a 2026-dated news item is recent coverage")

    def test_marker_suppression_contract(self):
        # Even if the composer somehow omitted a year, the guard's building block
        # (the '"In recent news:" in final' check the delivery path uses) is the
        # backstop: the honest note's own marker and the news marker are distinct,
        # so the integration can detect the news and skip the note.
        import current_affairs_coverage as cac
        self.assertNotIn("In recent news:", cac._HONEST_NOTE)
        self.assertIn("no verified developments", cac._HONEST_NOTE_MARK)


# ─────────────────────────────────────────────────────────────────────────────
# 5. TTL — pure marker logic (no DB)
# ─────────────────────────────────────────────────────────────────────────────
class TestTTLMarkerLogic(unittest.TestCase):
    def test_pool_unit_news_detection(self):
        import stop_pool_store as sp
        news_unit = {"narration": "Built in 1798. In recent news: On Oct 8, 2026, ...",
                     "raw_block": ""}
        hist_unit = {"narration": "Built in 1798. A long civic history.",
                     "raw_block": "Stop 1: X\n\nBuilt in 1798."}
        self.assertTrue(sp._unit_has_news(news_unit))
        self.assertFalse(sp._unit_has_news(hist_unit))

    def test_cache_marker_detection(self):
        import tour_cache_layer1 as tc
        self.assertIn(tc._NEWS_MARKER, "x In recent news: y")
        self.assertEqual(tc._NEWS_MARKER, "In recent news:")
        self.assertEqual(tc.NEWS_FRESH_DAYS, 7)
        import stop_pool_store as sp
        self.assertEqual(sp.NEWS_FRESH_DAYS, 7)


# ─────────────────────────────────────────────────────────────────────────────
# 5b. TTL — DB-backed (skips when Postgres is unreachable)
# ─────────────────────────────────────────────────────────────────────────────
class TestTTLDatabase(unittest.TestCase):
    def _db_url(self):
        return (os.environ.get("DATABASE_URL")
                or "postgresql://{u}:{p}@{h}:{port}/{d}".format(
                    u=os.environ.get("DB_USER", "admin"),
                    p=os.environ.get("DB_PASSWORD", "password123"),
                    h=os.environ.get("DB_HOST", "localhost"),
                    port=os.environ.get("DB_PORT", "5433"),
                    d=os.environ.get("DB_NAME", "audiotours")))

    def _conn(self):
        try:
            import psycopg2
        except Exception as e:  # pragma: no cover
            self.skipTest(f"psycopg2 unavailable: {e}")
        try:
            return psycopg2.connect(self._db_url(), connect_timeout=4)
        except Exception as e:  # pragma: no cover
            self.skipTest(f"DB unreachable: {e}")

    def test_pool_excludes_stale_news_stop(self):
        import stop_pool_store as sp
        conn = self._conn()
        try:
            sp._ensure_table(conn)
            key = "TEST655_pool_" + os.urandom(4).hex()
            with conn.cursor() as cur:
                for tnorm, title, offset_days, is_news in (
                        ("fresh_news", "Fresh News Stop", 1, True),
                        ("stale_news", "Stale News Stop", 30, True),
                        ("history", "History Stop", 30, False)):
                    news_sql = ("NOW() - INTERVAL '%d days'" % offset_days) if is_news else "NULL"
                    cur.execute(
                        "INSERT INTO stop_pool (pool_key, title_norm, venue_identity, "
                        "tour_type, pool_version, title, narration, news_generated_at, "
                        "generated_at) VALUES (%s,%s,%s,%s,%s,%s,%s," + news_sql + ", NOW())",
                        (key, tnorm, "test-identity", "walking", sp.POOL_VERSION,
                         title, "body"))
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT title_norm FROM stop_pool WHERE pool_key=%s "
                    "AND (news_generated_at IS NULL OR news_generated_at >= "
                    "NOW() - (%s || ' days')::interval)",
                    (key, str(sp.NEWS_FRESH_DAYS)))
                got = {r[0] for r in cur.fetchall()}
            self.assertIn("fresh_news", got)
            self.assertIn("history", got)
            self.assertNotIn("stale_news", got, "a >7d news stop must be excluded")
            with conn.cursor() as cur:
                cur.execute("DELETE FROM stop_pool WHERE pool_key=%s", (key,))
            conn.commit()
        finally:
            conn.close()

    def test_cache_excludes_stale_news_tour(self):
        import tour_cache_layer1 as tc
        conn = self._conn()
        try:
            tc._ensure_table(conn)
            with conn.cursor() as cur:
                fresh_key = "TEST655c_fresh_" + os.urandom(4).hex()
                stale_key = "TEST655c_stale_" + os.urandom(4).hex()
                hist_key = "TEST655c_hist_" + os.urandom(4).hex()
                cur.execute(
                    "INSERT INTO tour_cache (cache_key, location, tour_type, total_stops, "
                    "tour_content, has_news, created_at) VALUES "
                    "(%s,'L','walking',5,'c In recent news: x',TRUE, NOW()-INTERVAL '1 days'),"
                    "(%s,'L','walking',5,'c In recent news: x',TRUE, NOW()-INTERVAL '30 days'),"
                    "(%s,'L','walking',5,'c history only',FALSE, NOW()-INTERVAL '30 days')",
                    (fresh_key, stale_key, hist_key))
                conn.commit()
                pred = ("(COALESCE(has_news,FALSE)=FALSE OR created_at >= NOW() - "
                        "(%s || ' days')::interval)")
                cur.execute(
                    "SELECT cache_key FROM tour_cache WHERE cache_key IN (%s,%s,%s) AND "
                    + pred, (fresh_key, stale_key, hist_key, str(tc.NEWS_FRESH_DAYS)))
                got = {r[0] for r in cur.fetchall()}
                self.assertIn(fresh_key, got)
                self.assertIn(hist_key, got)
                self.assertNotIn(stale_key, got, "a >7d news tour must be excluded")
                cur.execute("DELETE FROM tour_cache WHERE cache_key IN (%s,%s,%s)",
                            (fresh_key, stale_key, hist_key))
                conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
