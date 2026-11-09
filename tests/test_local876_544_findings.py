"""LOCAL-876 — tour 544 findings (server side).

Two findings, both on tour 544 (ouVCyG8V, HCMC walking tour):

FINDING 1 — header vs narration contradiction.
  Stop 1 (Notre-Dame Cathedral Basilica of Saigon) shipped
      Specific Examples: Stunning neo-Romanesque architecture, ...
  while the narration / evidence describe the cathedral as neo-Gothic.  The
  Type/Specialty and Specific Examples HEADER lines were restored from the poi
  dict (LOCAL-866) and never reconciled with the body or the evidence.  The new
  stop_header_consistency reconciler must drop the contradicted header style
  (prefer the fact sheet when one exists; otherwise the body/evidence wins), and
  keep the correct body.  Tested with the EXACT strings.

FINDING 2 — the "★ 7.5 · New" badge.
  map_delivery's RANK_PRIOR_SCORE = 7.5 was shown as a rating for a tour with
  NO ratings.  The shown number must be ``display_rating`` = None when unrated
  (the app then shows "New" with no number), while ``rank_score`` keeps the 7.5
  prior for SORTING.

All pure: no DB, no network, no LLM.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import stop_header_consistency as shc  # noqa: E402


# ── The exact tour-544 Stop 1 block (header neo-Romanesque, narration neo-Gothic)
TOUR544_STOP1 = """Stop 1: Notre-Dame Cathedral Basilica of Saigon

Coordinates: 10.779785, 106.699020

Type/Specialty: Historical Landmark

Specific Examples: Stunning neo-Romanesque architecture, beautiful stained glass windows, and a peaceful garden.

Orientation: You are about to embark on a walking journey. The cathedral here was \
established in 1863 and completed in 1880. Its neo-Gothic design, with a soaring \
facade of red Marseille brick, rises over Paris Commune Square.

Directions: Continue to Saigon Central Post Office — it is about a minute's walk away.
"""


# ─── Finding 1 — header-line style consistency ────────────────────────────────

class TestFinding1HeaderConsistency:
    def test_neo_romanesque_header_dropped_when_body_says_neo_gothic(self):
        """The EXACT tour-544 case: the header's neo-Romanesque claim is dropped
        because the body states neo-Gothic; the body is untouched."""
        new, reasons = shc.reconcile_stop_block(TOUR544_STOP1, poi=None)
        low = new.lower()
        # the contradicted header style is gone from the Specific Examples line
        assert "neo-romanesque" not in low
        assert "romanesque" not in low
        # the rest of the Specific Examples line survives
        assert "stained glass windows" in low
        assert "peaceful garden" in low
        # the body's correct style is retained
        assert "neo-gothic" in low
        # a reason was recorded naming the dropped style and the contradiction
        assert any("romanesque" in r.lower() and "gothic" in r.lower() for r in reasons)

    def test_idempotent(self):
        once, _ = shc.reconcile_stop_block(TOUR544_STOP1, poi=None)
        twice, reasons2 = shc.reconcile_stop_block(once, poi=None)
        assert twice == once
        assert reasons2 == []

    def test_fact_sheet_style_wins_over_contradicting_header(self):
        """When the stop has a fact sheet naming the style, a header style that
        disagrees is dropped — the fact sheet is authoritative."""
        poi = {
            "name": "Notre-Dame Cathedral Basilica of Saigon",
            "stop_number": 1,
            "fact_sheet": {"architecture": "Gothic Revival (neo-Gothic) architecture"},
        }
        block = ("Stop 1: Notre-Dame Cathedral Basilica of Saigon\n\n"
                 "Specific Examples: Stunning neo-Romanesque architecture, "
                 "beautiful stained glass windows.\n")
        new, reasons = shc.reconcile_stop_block(block, poi=poi)
        assert "romanesque" not in new.lower()
        assert "stained glass windows" in new.lower()
        assert any("fact sheet" in r.lower() for r in reasons)

    def test_evidence_path_via_reconcile_stop_headers(self):
        """With no style word in the body, evidence passed per-stop still drives
        the contradiction (the LOCAL-872 claim-gate idea on the header)."""
        text = (
            "Step-by-step audio guided tour.\n\n"
            "Stop 1: Old Cathedral\n\n"
            "Type/Specialty: neo-Romanesque church\n\n"
            "Orientation: A plain description that names no style.\n"
        )
        out = shc.reconcile_stop_headers(
            text, poi_list=None,
            stop_evidence={1: ["The cathedral is a Gothic Revival landmark."]})
        assert "romanesque" not in out.lower()

    def test_no_style_in_header_is_untouched(self):
        """A header with no architectural style word is left exactly as-is."""
        block = ("Stop 1: Ben Thanh Market\n\n"
                 "Type/Specialty: Historic market\n\n"
                 "Specific Examples: Street food stalls, souvenirs, and local produce.\n\n"
                 "Orientation: A busy covered market with a neo-Gothic clock tool nearby.\n")
        new, reasons = shc.reconcile_stop_block(block, poi=None)
        assert new == block
        assert reasons == []

    def test_agreeing_style_is_kept(self):
        """When header and body agree on the style, nothing is dropped."""
        block = ("Stop 1: Old Cathedral\n\n"
                 "Specific Examples: Beautiful neo-Gothic architecture and stained glass.\n\n"
                 "Orientation: Its neo-Gothic facade dominates the square.\n")
        new, reasons = shc.reconcile_stop_block(block, poi=None)
        assert "neo-gothic" in new.lower()
        assert reasons == []

    def test_whole_line_dropped_when_only_the_contradicted_style_remains(self):
        """If the Specific Examples line is ONLY the contradicted style, the whole
        line is dropped rather than left as an empty label."""
        block = ("Stop 1: Old Cathedral\n\n"
                 "Specific Examples: neo-Romanesque architecture.\n\n"
                 "Orientation: Its neo-Gothic design rises over the square.\n")
        new, reasons = shc.reconcile_stop_block(block, poi=None)
        assert "specific examples" not in new.lower()
        assert reasons

    def test_full_tour_text_reconcile_runs_over_all_stops(self):
        """reconcile_stop_headers applies to every Stop N: block and returns text."""
        text = "Intro line.\n\n" + TOUR544_STOP1
        out = shc.reconcile_stop_headers(text, poi_list=None)
        assert out.startswith("Intro line.")
        assert "neo-romanesque" not in out.lower()
        assert "neo-gothic" in out.lower()

    def test_style_token_helpers(self):
        assert shc.style_tokens("Stunning neo-Romanesque architecture") == ["romanesque"]
        assert shc.style_tokens("Gothic Revival design") == ["gothic"]
        assert shc.style_tokens("a peaceful garden") == []
        # mutually-exclusive families clash
        assert shc.contradicting_style("neo-Romanesque", "neo-Gothic") is not None
        # same family does not clash
        assert shc.contradicting_style("Gothic Revival", "neo-Gothic") is None


# ─── Finding 2 — unrated tour shows "New", never the 7.5 prior ────────────────

class TestFinding2RatingDisplay:
    def test_orchestrator_compute_score_unrated_display_is_none(self):
        import tour_rating_service as rating_svc
        r = rating_svc.compute_score([])
        assert r["count"] == 0
        assert r["display_rating"] is None   # the app shows "New", no number
        assert r["label"] == "New"
        assert r["score"] == 7.5             # kept for back-compat / placeholder

    def test_orchestrator_compute_score_rated_display_is_the_score(self):
        import tour_rating_service as rating_svc
        r = rating_svc.compute_score([9])
        assert r["count"] == 1
        assert r["display_rating"] == r["score"]
        assert r["display_rating"] is not None

    def test_orchestrator_evaluated_prior_unrated_still_new(self):
        """Even with an evaluated prior (editor score), an unrated tour has no
        shown number — display_rating is None."""
        import tour_rating_service as rating_svc
        r = rating_svc.compute_score([], prior=6.0)
        assert r["count"] == 0
        assert r["display_rating"] is None

    def test_map_delivery_payload_unrated(self):
        app = _import_map_delivery_app()
        p = app._rating_payload([], None, None, False)
        assert p["rating_count"] == 0
        assert p["display_rating"] is None            # app shows "New"
        assert p["rank_score"] == app.RANK_PRIOR_SCORE  # 7.5 KEPT for sorting

    def test_map_delivery_payload_rated(self):
        app = _import_map_delivery_app()
        p = app._rating_payload([9, 9, 9, 9], None, None, False)
        assert p["rating_count"] == 4
        assert p["display_rating"] == p["rating_score"]
        assert p["display_rating"] is not None

    def test_map_delivery_rank_score_independent_of_display(self):
        """rank_score (the sort key) uses the 7.5 prior for an unrated tour and
        is unchanged by the display_rating fix — list order is unaffected."""
        app = _import_map_delivery_app()
        unrated = app._rating_payload([], None, None, False)
        rated_low = app._rating_payload([1, 1, 1, 1], None, None, False)
        # an unrated tour (rank 7.5) still sorts above a tour of four 1s
        assert unrated["rank_score"] > rated_low["rank_score"]
        # yet the unrated tour shows no number
        assert unrated["display_rating"] is None


def _import_map_delivery_app():
    md = os.path.join(os.path.dirname(os.path.dirname(__file__)), "map_delivery")
    if md not in sys.path:
        sys.path.insert(0, md)
    import importlib
    return importlib.import_module("app")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
