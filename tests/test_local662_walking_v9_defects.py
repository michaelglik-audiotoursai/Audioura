#!/usr/bin/env python3
"""test_local662_walking_v9_defects.py — LOCAL-662 guard for the four tour-557-v9
Boston-walking defects.

Kiro 5.5 scored tour 557 v9 (the Boston "Massachusetts politics and current
affairs" walking tour) 5.5/10 for four defects. This suite asserts, offline and
deterministically, that each is fixed:

  1. An UNVERIFIED STOP. A WALKING tour's stop-existence gate must ENFORCE
     (Wikidata/OSM resolve or GEO-CHECK replacement, else N-1), while a museum
     tour keeps the shared-stack mode. Checked at the mode-resolver seam
     (stop_existence_gate.get_gate_mode_for_category) because the full gate needs
     a DB + network -- the resolver is the one deterministic decision the live
     gate makes per tour.
  2. A LEAKED EDITOR MARKER. '<!-- LOCAL-628:stop-editor:v1 -->' must never reach
     the delivered text / TTS / critic. The news pass strips it before injecting,
     and strip_marker removes it; the 'markers' detector shape ('<!--') is gone.
  3. TOO MUCH NEWS. research_news_for_stops caps at 2 stops / 3 items, newest
     first; _attribution_suffix never emits a '(Reported by ...)' source list.
  4. A SENTENCE COLLISION. '...civic architecture could Seven years later...' (a
     dangling modal welded to a capitalised sentence-start) is repaired to
     '...civic architecture. Seven years later...', and the general collision
     shape is gone -- while legitimate prose ('to Paris', 'is Mona Lisa', 'had
     Boston') is untouched.

Run: python3 -m pytest tests/test_local662_walking_v9_defects.py -q
"""
import datetime as _dt
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIXTURE = os.path.join(_HERE, "fixtures", "local662",
                        "tour_557_v9_stop3_collision_and_marker.txt")

# The general mid-clause collision shape (same as the LOCAL-654 guard): a
# lowercase word, a space, a Capitalised real word, no clause/sentence punctuation.
_COLLISION_RE = re.compile(r"(?<![.!?:;,)\]\"'\u201d\u2019])\b([a-z]{3,})\s([A-Z][a-z]{2,})")


def _collisions(text):
    return {(m.group(1), m.group(2)) for m in _COLLISION_RE.finditer(text or "")}


# -- Defect 1: WALKING tours enforce the stop-existence gate ------------------
class TestDefect1WalkingEnforce(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ("STOP_EXISTENCE_GATE_MODE",
                                 "WALKING_EXISTENCE_GATE_ENFORCE",
                                 "DISABLE_STOP_EXISTENCE_GATE",
                                 "ENABLE_STOP_EXISTENCE_GATE")}
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _mode(self, category):
        import importlib
        import stop_existence_gate as g
        importlib.reload(g)
        return g.get_gate_mode_for_category(category)

    def test_log_only_shared_stack_walking_forces_enforce(self):
        os.environ["STOP_EXISTENCE_GATE_MODE"] = "log_only"
        self.assertEqual(self._mode("walking"), "enforce")
        self.assertEqual(self._mode("specialized"), "enforce")

    def test_museum_and_dining_keep_global_mode(self):
        os.environ["STOP_EXISTENCE_GATE_MODE"] = "log_only"
        self.assertEqual(self._mode("museum"), "log_only")
        self.assertEqual(self._mode("restaurant"), "log_only")

    def test_explicit_off_wins_even_for_walking(self):
        os.environ["STOP_EXISTENCE_GATE_MODE"] = "off"
        self.assertEqual(self._mode("walking"), "off")

    def test_walking_override_can_be_disabled(self):
        os.environ["STOP_EXISTENCE_GATE_MODE"] = "log_only"
        os.environ["WALKING_EXISTENCE_GATE_ENFORCE"] = "0"
        self.assertEqual(self._mode("walking"), "log_only")

    def test_already_enforce_stays_enforce(self):
        os.environ["STOP_EXISTENCE_GATE_MODE"] = "enforce"
        self.assertEqual(self._mode("walking"), "enforce")
        self.assertEqual(self._mode("museum"), "enforce")

    def test_fetch_wikidata_coords_is_callable(self):
        import stop_existence_gate as g
        self.assertTrue(callable(getattr(g, "_fetch_wikidata_coords", None)))


# -- Defect 2: the editor marker never reaches delivered text -----------------
class TestDefect2NoLeakedMarker(unittest.TestCase):
    def test_news_pass_strips_marker_before_injecting(self):
        import stop_editor as se
        import current_affairs_news as ca
        tour = ("Stop 1: Faneuil Hall\n\nBody one.\n\n"
                "Stop 5: Massachusetts State House\n\nState body.\n\n"
                "Directions: Walk on.\n" + se.EDITED_MARKER + "\n")
        self.assertTrue(se.already_edited(tour))
        stripped = se.strip_marker(tour)
        out, n = ca.inject_news_into_text(
            stripped,
            {"Massachusetts State House": {
                "text": "Last month, the legislature met, according to WGBH.",
                "sources": [{"source": "WGBH"}]}})
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("<!--", out)
        self.assertNotIn("LOCAL-628:stop-editor", out)

    def test_markers_detector_shape_absent_in_fixture_after_strip(self):
        import stop_editor as se
        with open(_FIXTURE, encoding="utf-8") as f:
            tour = f.read()
        self.assertIn("<!--", tour)
        delivered = se.strip_marker(tour)
        self.assertNotIn("<!--", delivered)
        self.assertNotIn("-->", delivered)

    def test_strip_marker_idempotent(self):
        import stop_editor as se
        tour = "Stop 1: X\n\nBody.\n" + se.EDITED_MARKER + "\n"
        once = se.strip_marker(tour)
        self.assertEqual(se.strip_marker(once), once)


# -- Defect 3: news is capped and carries no source-list parenthetical --------
class TestDefect3NewsCapAndAttribution(unittest.TestCase):
    REQ = ("Walking tour in Boston dedicated to Massachusetts politics and "
           "current affairs, Boston, MA")
    NOW = _dt.date(2026, 10, 9)

    def _items(self):
        return {
            "A": {"title": "Governor signs budget", "source": "State House News Service",
                  "date": "Oct 8, 2026", "link": "l1",
                  "snippet": ("Massachusetts Governor Healey and the legislature at the "
                              "State House passed a budget in Boston.")},
            "B": {"title": "Gubernatorial debate", "source": "WGBH",
                  "date": "Oct 7, 2026", "link": "l2",
                  "snippet": ("Massachusetts gubernatorial debate; the governor and "
                              "legislature clashed at the State House in Boston.")},
            "C": {"title": "City council vote", "source": "Boston Herald",
                  "date": "Oct 6, 2026", "link": "l3",
                  "snippet": ("The Boston City Council and mayor voted at City Hall "
                              "in Massachusetts.")},
            "D": {"title": "Mayor at City Hall", "source": "NBC Boston",
                  "date": "Oct 5, 2026", "link": "l4",
                  "snippet": ("The Boston mayor and city council met at City Hall, "
                              "Massachusetts.")},
            "E": {"title": "Old council measure", "source": "Globe",
                  "date": "Oct 1, 2026", "link": "l5",
                  "snippet": ("A Boston City Council ordinance at City Hall, "
                              "Massachusetts, older item.")},
        }

    def test_cap_two_stops_three_items_newest_first(self):
        import current_affairs_news as ca
        items = self._items()

        def serp(q, tbs="qdr:m", num=8):
            return list(items.values())

        def fetch(url):
            for v in items.values():
                if v["link"] == url:
                    return (v["snippet"], None)
            return ("", None)

        def answer(prompt, model=None, max_tokens=None):
            return {"text": "On October 8, 2026, the governor acted, according to "
                            "the State House News Service [1].", "error": ""}

        stops = ["Massachusetts State House", "Boston City Hall", "Faneuil Hall",
                 "Old State House", "Boston Common"]
        log = ca.research_news_for_stops(self.REQ, stops, serp=serp, fetch=fetch,
                                         answer=answer, fresh_days=365, now=self.NOW)
        self.assertLessEqual(len(log["by_stop"]), ca.NEWS_MAX_STOPS)
        total = sum(len(v["articles"]) for v in log["by_stop"].values())
        self.assertLessEqual(total, ca.NEWS_MAX_ITEMS_TOTAL)
        kept_links = {a["link"] for v in log["by_stop"].values() for a in v["articles"]}
        self.assertNotIn("l5", kept_links, "oldest item must be dropped first")
        self.assertIn("capped", log)

    def test_attribution_suffix_is_always_empty(self):
        import current_affairs_news as ca
        self.assertEqual(ca._attribution_suffix("anything", ["WGBH"]), "")
        self.assertEqual(ca._attribution_suffix("x", ["A", "B"]), "")

    def test_injected_news_has_no_reported_by_parenthetical(self):
        import current_affairs_news as ca
        by_stop = {"Boston City Hall": {
            "text": "On October 6, 2026, the city council voted, the Boston Herald reported.",
            "sources": [{"source": "Boston Herald"}]}}
        text = ("Stop 1: Boston City Hall\n\nBuilt in 1968.\n\n"
                "Directions: Walk on.\n")
        out, n = ca.inject_news_into_text(text, by_stop)
        self.assertEqual(n, 1)
        self.assertNotIn("Reported by", out)
        self.assertNotIn("(Reported", out)

    def test_composer_prompt_requires_inline_source(self):
        import current_affairs_news as ca
        captured = {}

        def spy(prompt, model=None, max_tokens=None):
            captured["p"] = prompt
            return {"text": "On October 8, 2026, the governor acted, the Globe "
                            "reported [1].", "error": ""}

        item = {"title": "t", "source": "Globe", "snippet": "body text here enough",
                "link": "l", "_parsed_date": "2026-10-08",
                "_exact_date": "2026-10-08", "_date_precision": ca.DATE_EXACT}
        ca.compose_news_sentences("Massachusetts politics", [item], answer=spy,
                                  locale="Boston, MA")
        self.assertIn("source outlet", captured["p"].lower())


# -- Defect 4: the dangling-modal sentence collision is repaired --------------
class TestDefect4CollisionRepair(unittest.TestCase):
    REAL = ("In 1969, the American Institute of Architects awarded the building "
            "its Honor Award, placing City Hall into the national conversation "
            "about what civic architecture could Seven years later, in 1976, a "
            "poll of architects and critics ranked it among the greatest.")

    def test_real_tour557_collision_repaired(self):
        import stop_editor as se
        self.assertIsNotNone(se.detect_broken_join(self.REAL))
        out, n = se.repair_broken_joins(self.REAL)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("could Seven", out)
        self.assertIn("architecture. Seven", out)
        self.assertIsNone(se.detect_broken_join(out))
        self.assertEqual(se.repair_broken_joins(out)[1], 0)

    def test_detect_dangling_modal_join_names_the_shape(self):
        import stop_editor as se
        self.assertIsNotNone(se.detect_dangling_modal_join(
            "architecture could Seven years later"))

    def test_legitimate_prose_untouched(self):
        import stop_editor as se
        for ok in (
            "He lived in Florence for many years before moving to Rome.",
            "The painting is Mona Lisa today, admired by millions.",
            "She traveled to Paris and London that summer.",
            "It was created to honor the fallen soldiers.",
            "They had Boston in mind when they planned the route.",
            "What the architects could do shaped the skyline.",
            "The American Institute of Architects met in Boston.",
        ):
            out, n = se.repair_broken_joins(ok)
            self.assertEqual(n, 0, f"false positive on: {ok!r} -> {out!r}")
            self.assertEqual(out, ok.strip())

    def test_fixture_collision_removed_by_text_guard(self):
        import stop_editor as se
        with open(_FIXTURE, encoding="utf-8") as f:
            tour = f.read()
        self.assertIn(("could", "Seven"), _collisions(tour))
        out, n = se.repair_broken_joins_in_text(tour)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("could Seven", out)
        self.assertNotIn(("could", "Seven"), _collisions(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
