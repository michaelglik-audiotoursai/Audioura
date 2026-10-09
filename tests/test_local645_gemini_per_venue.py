"""test_local645_gemini_per_venue.py — LOCAL-645 (cost prototype 1).

GEMINI_PER_VENUE replaces the per-stop grounded Gemini search with ONE grounded
research pass per MUSEUM, cached per venue for 30 days (same venue_preflight_cache
pattern). These tests prove the four properties the ticket requires, all with
injected fakes and ZERO network / ZERO paid calls:

  1. REQUEST COUNT, FLAG ON. A stop run with the flag on issues exactly ONE
     grounded request (the venue pass) and narrates the stop UNGROUNDED using the
     venue material. No per-stop grounded search.

  2. CACHE HITS. A second stop of the same venue — and a later tour of the same
     museum — reuse the cached venue pass: zero additional grounded requests.

  3. PER-WORK FALLBACK. When the venue pass returns "NO MATERIAL FOUND" for a
     work, that stop (and only that stop) falls back to a per-work grounded
     request, within the per-stop budget.

  4. NO CHANGE, FLAG OFF. With the flag unset, the loop grounds exactly as the
     LOCAL-594 cut does — the venue pass is never fetched and the stop's grounded
     request count is identical to the flag-off path.

Run:  python3 -m unittest tests.test_local645_gemini_per_venue -v
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# A key must be present or the Gemini wrappers short-circuit before issuing a
# request. The network is faked below, so the value never reaches Google.
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

# Keep the loop's append-only candidate log OUT of the tracked
# story_loop_candidates.jsonl — point it at a throwaway temp file for this suite.
import tempfile  # noqa: E402
os.environ["STORY_LOOP_CANDIDATE_LOG"] = os.path.join(
    tempfile.gettempdir(), "local645_candidates.jsonl")

import story_leads  # noqa: E402
import story_production_loop as spl  # noqa: E402
import work_story_searcher  # noqa: E402
import snippet_ranker  # noqa: E402
import object_record  # noqa: E402


# ─── a fake Gemini wire at the story_leads boundary ──────────────────────────
# We fake story_leads.gemini_with_sources so BOTH the venue pass (grounded) and
# the per-stop narrate (grounded or not) go through our counter. This exercises
# the REAL run_for_stop gate and the REAL venue_research attribution logic; only
# the network is replaced.
class _Wire:
    def __init__(self, venue_material_by_work):
        # work title -> the paragraph the venue pass returns for it, or '' to make
        # the pass emit "NO MATERIAL FOUND" for that work (forcing fallback).
        self.venue_material = venue_material_by_work
        self.grounded = 0
        self.ungrounded = 0
        self.venue_passes = 0
        self.perwork_grounded = 0

    def gemini_with_sources(self, prompt, model=None, resolve=True, timeout=90,
                            grounded=True):
        if grounded:
            self.grounded += 1
        else:
            self.ungrounded += 1

        # The venue research prompt names the venue block and lists works.
        if "research this museum/venue" in prompt:
            self.venue_passes += 1
            paras = ["The McMullen Museum of Art is the art museum of Boston "
                     "College, known for scholarly loan exhibitions."]
            for work, material in self.venue_material.items():
                if material:
                    paras.append(f"{work}: {material}")
                else:
                    paras.append(f"{work}: NO MATERIAL FOUND")
            return {"text": "\n\n".join(paras),
                    "sources": [{"domain": "bc.edu", "url": "https://bc.edu/x"}],
                    "supports": [], "queries": ["mcmullen miro"], "error": ""}

        # Otherwise this is a per-stop narrate (r1) or adjudicate (r2).
        if grounded:
            # A grounded narrate here is the PER-WORK FALLBACK.
            self.perwork_grounded += 1
        if "PART 2" in prompt or "ADJUDICATE" in prompt or "earlier answer" in prompt:
            text = ("PART 1\nCONFIRMED In 1961 the artist destroyed the first "
                    "edition — the museum's own record.\n"
                    "PART 2\nIn 1961 the artist destroyed the first edition of the "
                    "work after the printer sanded the stones, and only eleven "
                    "proofs survived.")
        else:
            text = ("In 1961 the artist destroyed the first edition of the work "
                    "after the printer sanded the stones. Only eleven proofs "
                    "survived the destruction.")
        return {"text": text,
                "sources": [{"domain": "museum.example",
                             "url": "https://museum.example/x"}],
                "supports": [], "queries": (["q"] if grounded else []), "error": ""}

    def serp_search(self, query):
        return ([{"title": "First edition destroyed 1961",
                  "snippet": ("In 1961 the artist destroyed the first edition "
                              "after the printer sanded the stones."),
                  "url": "https://museum.example/record",
                  "domain": "museum.example"}], 0.0)


def _matrix(work="Le Lézard aux plumes d'or"):
    return {
        "canonical_title": work,
        "artist": "Joan Miró",
        "publisher": "Louis Broder",
        "printed_by": "Mourlot Frères",
        "printer": "Mourlot Frères",
        "collaborator": "Tériade",
        "credit_line": "Gift of the Lamar Family",
        "medium": "lithograph",
        "venue_name": "McMullen Museum of Art",
    }


_STOP_TEXT = ("The work is a livre d'artiste. Mourlot Frères printed it and "
              "Tériade published related suites. The Lamar Family gave it.")


class _LoopEnv:
    """Context manager: patch every network boundary run_for_stop reaches, plus a
    fake in-memory venue-research cache so cache behaviour is testable with no DB.
    Restores everything on exit."""

    def __init__(self, wire, flag_on, max_grounded=1, max_credit_lines=4,
                 fake_cache=None):
        self.wire = wire
        self.flag_on = flag_on
        self.max_grounded = max_grounded
        self.max_credit_lines = max_credit_lines
        # fake_cache: dict cache_key -> result (shared across stops/tours to prove
        # reuse). None means "no cache" (every venue pass runs fresh).
        self.fake_cache = fake_cache

    def __enter__(self):
        self._orig = {
            "sl_gws": story_leads.gemini_with_sources,
            "serp": work_story_searcher._serp_search,
            "fetch": snippet_ranker.fetch_pages_for_top_snippets,
            "enrich": object_record.enrich_matrix,
            "maxcl": spl.MAX_CREDIT_LINES,
            "maxg": spl.MAX_GROUNDED_PER_STOP,
            "bestof": spl.BEST_OF,
            "stopat": spl.STOP_AT,
            "flag": os.environ.get(story_leads.GEMINI_PER_VENUE_ENV),
            "cget": story_leads._venue_research_cache_get,
            "cput": story_leads._venue_research_cache_put,
        }
        story_leads.gemini_with_sources = self.wire.gemini_with_sources
        work_story_searcher._serp_search = self.wire.serp_search
        snippet_ranker.fetch_pages_for_top_snippets = lambda raw, max_fetches=3: None
        object_record.enrich_matrix = lambda m, url, verbose=False: (m, {})
        spl.MAX_CREDIT_LINES = self.max_credit_lines
        spl.MAX_GROUNDED_PER_STOP = self.max_grounded
        spl.BEST_OF = True
        spl.STOP_AT = 999
        if self.flag_on:
            os.environ[story_leads.GEMINI_PER_VENUE_ENV] = "1"
        else:
            os.environ.pop(story_leads.GEMINI_PER_VENUE_ENV, None)

        # Fake the DB cache with an in-memory dict (or always-miss when None).
        if self.fake_cache is not None:
            def _cget(venue, city, db_url):
                res = self.fake_cache.get(
                    story_leads._venue_research_cache_key(venue, city))
                if res is None:
                    return None
                r = dict(res)
                r["cached"] = True
                return r

            def _cput(venue, city, result, db_url):
                r = dict(result)
                r["cached"] = False
                self.fake_cache[
                    story_leads._venue_research_cache_key(venue, city)] = r
        else:
            def _cget(venue, city, db_url):
                return None

            def _cput(venue, city, result, db_url):
                return None
        story_leads._venue_research_cache_get = _cget
        story_leads._venue_research_cache_put = _cput
        return self

    def __exit__(self, *exc):
        story_leads.gemini_with_sources = self._orig["sl_gws"]
        work_story_searcher._serp_search = self._orig["serp"]
        snippet_ranker.fetch_pages_for_top_snippets = self._orig["fetch"]
        object_record.enrich_matrix = self._orig["enrich"]
        spl.MAX_CREDIT_LINES = self._orig["maxcl"]
        spl.MAX_GROUNDED_PER_STOP = self._orig["maxg"]
        spl.BEST_OF = self._orig["bestof"]
        spl.STOP_AT = self._orig["stopat"]
        story_leads._venue_research_cache_get = self._orig["cget"]
        story_leads._venue_research_cache_put = self._orig["cput"]
        if self._orig["flag"] is None:
            os.environ.pop(story_leads.GEMINI_PER_VENUE_ENV, None)
        else:
            os.environ[story_leads.GEMINI_PER_VENUE_ENV] = self._orig["flag"]
        return False

    def run(self, work="Le Lézard aux plumes d'or"):
        return spl.run_for_stop(
            _matrix(work), _STOP_TEXT, exhibition="Miró at the McMullen",
            venue_url="", extra_entities=["Joan Miró"], verbose=False,
            venue="McMullen Museum of Art", city="Boston, MA")


# A venue pass that HAS material about the tour's one work.
_MATERIAL = {"Le Lézard aux plumes d'or":
             "In 1961 the artist destroyed the first edition after the printer "
             "sanded the stones; eleven proofs survived."}


class TestFlagOnRequestCount(unittest.TestCase):
    """(1) Flag ON: exactly one grounded request (the venue pass); the stop
    narrate is ungrounded."""

    def test_one_grounded_venue_pass_and_ungrounded_narrate(self):
        wire = _Wire(_MATERIAL)
        with _LoopEnv(wire, flag_on=True, fake_cache={}) as env:
            out = env.run()
        self.assertEqual(wire.venue_passes, 1,
                         "exactly one grounded venue research pass expected")
        self.assertEqual(wire.grounded, 1,
                         f"flag ON should issue exactly 1 grounded request "
                         f"(the venue pass), got {wire.grounded}")
        self.assertEqual(wire.perwork_grounded, 0,
                         "no per-work grounded request when the venue pass has "
                         "material about the work")
        # The stop's own grounded-request counter is 0 — the narrate was ungrounded.
        self.assertEqual(out.get("grounded_requests"), 0,
                         "the per-stop narrate must be ungrounded under the flag")
        self.assertGreater(wire.ungrounded, 0,
                           "the stop must narrate (ungrounded) at least once")


class TestCacheHits(unittest.TestCase):
    """(2) Cache hits: later stops and later tours of the same museum reuse the
    one venue pass."""

    def test_second_stop_same_venue_reuses_pass(self):
        wire = _Wire({
            "Le Lézard aux plumes d'or": _MATERIAL["Le Lézard aux plumes d'or"],
            "Au Soleil du Plafond": "Juan Gris collaborated on it in 1954.",
        })
        cache = {}
        with _LoopEnv(wire, flag_on=True, fake_cache=cache) as env:
            env.run("Le Lézard aux plumes d'or")
            self.assertEqual(wire.venue_passes, 1)  # first stop fetched it
            env.run("Au Soleil du Plafond")         # second stop, same venue
        self.assertEqual(wire.venue_passes, 1,
                         "the second stop of the same venue must REUSE the cached "
                         f"pass, not fetch a new one (got {wire.venue_passes})")
        self.assertEqual(wire.grounded, 1,
                         "only one grounded request for the whole venue")

    def test_later_tour_same_museum_reuses_pass(self):
        # Two separate tours (two independent runs) of the same museum share the
        # 30-day cache: the second tour issues zero grounded venue passes.
        cache = {}
        wire1 = _Wire(_MATERIAL)
        with _LoopEnv(wire1, flag_on=True, fake_cache=cache) as env:
            env.run()
        self.assertEqual(wire1.venue_passes, 1)
        wire2 = _Wire(_MATERIAL)
        with _LoopEnv(wire2, flag_on=True, fake_cache=cache) as env:
            env.run()
        self.assertEqual(wire2.venue_passes, 0,
                         "a later tour of the same museum must reuse the cached "
                         "venue pass (zero grounded requests)")
        self.assertEqual(wire2.grounded, 0,
                         "cache hit => zero grounded requests on the second tour")

    def test_venue_research_use_cache_false_forces_fresh(self):
        # The function-level control: use_cache=False always issues the pass.
        cache = {}
        wire = _Wire(_MATERIAL)
        with _LoopEnv(wire, flag_on=True, fake_cache=cache):
            story_leads.venue_research("McMullen Museum of Art", "Boston, MA",
                                       works=["Le Lézard aux plumes d'or"],
                                       use_cache=True)
            self.assertEqual(wire.venue_passes, 1)
            story_leads.venue_research("McMullen Museum of Art", "Boston, MA",
                                       works=["Le Lézard aux plumes d'or"],
                                       use_cache=False)
            self.assertEqual(wire.venue_passes, 2,
                             "use_cache=False must force a fresh grounded pass")


class TestPerWorkFallback(unittest.TestCase):
    """(3) Per-work fallback: when the venue pass found nothing about a work, that
    stop issues a per-work grounded request."""

    def test_fallback_fires_when_venue_pass_empty_for_work(self):
        # The venue pass returns NO MATERIAL FOUND for this work (material='').
        wire = _Wire({"Le Lézard aux plumes d'or": ""})
        with _LoopEnv(wire, flag_on=True, fake_cache={}) as env:
            out = env.run("Le Lézard aux plumes d'or")
        self.assertEqual(wire.venue_passes, 1, "venue pass still runs once")
        # The venue pass (1 grounded) + the per-work fallback (1 grounded) = 2.
        self.assertEqual(wire.perwork_grounded, 1,
                         "a per-work grounded fallback must fire when the venue "
                         "pass has nothing about the work")
        self.assertEqual(out.get("grounded_requests"), 1,
                         "the fallback counts as the stop's one grounded request")
        self.assertEqual(wire.grounded, 2,
                         "venue pass + one per-work fallback = 2 grounded requests")

    def test_no_fallback_when_venue_pass_has_material(self):
        wire = _Wire(_MATERIAL)
        with _LoopEnv(wire, flag_on=True, fake_cache={}) as env:
            out = env.run()
        self.assertEqual(wire.perwork_grounded, 0)
        self.assertEqual(out.get("grounded_requests"), 0)

    def test_split_work_material_maps_no_material_to_empty(self):
        # Unit-level proof of the attribution the fallback depends on.
        text = ("The venue is a museum.\n\n"
                "Le Lézard aux plumes d'or: In 1961 it was destroyed.\n\n"
                "Au Soleil du Plafond: NO MATERIAL FOUND")
        got = story_leads._split_work_material(
            text, ["Le Lézard aux plumes d'or", "Au Soleil du Plafond"])
        self.assertTrue(got["Le Lézard aux plumes d'or"])
        self.assertEqual(got["Au Soleil du Plafond"], "",
                         "NO MATERIAL FOUND must map to '' so the caller falls back")


class TestFlagOffNoChange(unittest.TestCase):
    """(4) Flag OFF: behaviour identical to the LOCAL-594 cut — no venue pass, the
    stop grounds exactly as before."""

    def test_flag_off_never_fetches_venue_pass(self):
        wire = _Wire(_MATERIAL)
        with _LoopEnv(wire, flag_on=False, fake_cache={}) as env:
            out = env.run()
        self.assertEqual(wire.venue_passes, 0,
                         "flag OFF must never fetch a venue research pass")
        # The stop grounds its first credit_line exactly like the LOCAL-594 cut.
        self.assertEqual(out.get("grounded_requests"), 1,
                         "flag OFF: the stop issues its one LOCAL-594 grounded r1")

    def test_flag_off_matches_grounded_count_of_cut(self):
        # Flag OFF grounded count == the shipped per-stop cut (MAX_GROUNDED_PER_STOP=1).
        wire_off = _Wire(_MATERIAL)
        with _LoopEnv(wire_off, flag_on=False, fake_cache={}, max_grounded=1) as env:
            out_off = env.run()
        self.assertEqual(out_off.get("grounded_requests"), 1)
        self.assertEqual(wire_off.venue_passes, 0)
        # And the enabled-check reflects the environment.
        self.assertFalse(story_leads.gemini_per_venue_enabled())

    def test_default_is_off(self):
        os.environ.pop(story_leads.GEMINI_PER_VENUE_ENV, None)
        self.assertFalse(story_leads.gemini_per_venue_enabled(),
                         "GEMINI_PER_VENUE must default OFF")


if __name__ == "__main__":
    unittest.main()
