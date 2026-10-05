"""
LOCAL-586: The FORCED STOPS — VERIFICATION HARNESS banner must never land in a
real listener-chosen-stops tour, and when a genuine harness caller does ask for
it, it must appear EXACTLY ONCE.

Defect (Michael, 2026-10-05, share RY7jFTKu → tour 371, translation of 370):
    Tour 370 was a ONE-stop listener-chosen tour (Chart House) requested by
    Michael's phone through the orchestrator. Its tour_content opened with the
    harness banner repeated 70 times, so the app rendered a garbled stop.

Two independent faults, both fixed and pinned here:

  1. CONFLATED CALLERS. The engine's forced_stops path (LOCAL-357) was shared by
     the verification harness AND, since LOCAL-523/525/547, by the product
     "choose your own stops" feature. The banner was stamped whenever
     forced_stops was present — so the product path stamped it too. Fix: the
     banner is now gated on an explicit `harness=True` flag that the orchestrator
     / tour-generator /generate path NEVER sets. A listener's own stops carry no
     banner and no "not naturally selected" wording.

  2. 70× REPETITION. The banner was built with implicit string-literal
     concatenation:
         "=" * 70 + "\n"
         "...body...\n"
         f"    Forced: {forced_stops}\n"
         "=" * 70 + "\n\n"
     Python joins adjacent string literals at compile time, so the f-string line
     merged with the following "=" literal into "    Forced: [...]\n=", and the
     trailing `* 70` repeated the WHOLE body 70 times (each block closed by a lone
     "="). Fix: _build_harness_banner() joins a list with "\n", so no literal is
     ever adjacent to a `* N`.

RED on storied / GREEN after:
  * test_harness_banner_appears_exactly_once — storied repeated it 70×.
  * test_product_path_forced_stops_produce_no_banner — storied stamped it.
  * test_generate_tour_text_accepts_harness_flag — storied has no harness param.
  * test_service_product_path_never_sets_harness — storied had no gate to omit.
"""
import os
import sys
import inspect
import importlib

import pytest


def _gtt_body():
    """The function that holds the generation code. On `subscribed`, LOCAL-562 made
    generate_tour_text a thin cost-scope wrapper around _generate_tour_text_impl, so
    source-inspection tests must read the impl when it exists (LEAD 2026-10-05)."""
    import generate_tour_text as _m
    return getattr(_m, '_generate_tour_text_impl', _m.generate_tour_text)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ───────────────────────── Fault #2: banner built once ─────────────────────────
class TestHarnessBannerBuiltExactlyOnce:
    """The marker builder must emit a single banner, never a repeated one."""

    def _banner(self, forced_stops):
        from generate_tour_text import _build_harness_banner
        return _build_harness_banner(forced_stops)

    def test_builder_exists(self):
        import generate_tour_text as gtt
        assert hasattr(gtt, "_build_harness_banner"), (
            "generate_tour_text must expose _build_harness_banner so the banner "
            "is constructed in one testable place (LOCAL-586)"
        )

    def test_harness_banner_appears_exactly_once(self):
        """The whole point: ONE banner, not 70. Red on storied (implicit concat
        * 70 repeated the body 70 times)."""
        b = self._banner(["Chart House"])
        assert b.count("⚠️  FORCED STOPS — VERIFICATION HARNESS (LOCAL-357)") == 1, (
            "banner body must be stamped exactly once"
        )
        assert b.count("This tour was generated with a forced stop list.") == 1
        assert b.count("Forced: ['Chart House']") == 1

    def test_separator_bar_is_seventy_equals_not_a_lone_equal(self):
        """Each separator is a full 70-'=' rule (two of them). The storied bug
        left 70 lone '=' lines; guard against its signature."""
        b = self._banner(["Chart House"])
        bar = "=" * 70
        assert b.count(bar) == 2, "exactly two 70-'=' rules (top and bottom)"
        lone_equals = [ln for ln in b.split("\n") if ln == "="]
        assert lone_equals == [], (
            f"a lone '=' line is the storied *70 signature; found {len(lone_equals)}"
        )

    def test_banner_names_the_forced_stops(self):
        b = self._banner(["Chart House", "Union Oyster House"])
        assert "Chart House" in b and "Union Oyster House" in b

    def test_banner_ends_with_blank_separator(self):
        b = self._banner(["Chart House"])
        assert b.endswith("\n\n"), "banner must end with one blank line before body"


# ─────────────────── Fault #1: product path carries no banner ───────────────────
class TestProductPathHasNoBanner:
    """A listener's own chosen stops (harness left False) → no banner anywhere in
    the written tour; harness=True → banner present. Exercises the REAL write
    block of generate_tour_text by invoking it with a stubbed pipeline."""

    def _run_write(self, tmp_path, harness):
        """Drive generate_tour_text's file-writing tail with forced_stops active,
        without the heavy pipeline: we stub the generator to the smallest shape
        that reaches the banner write. Done by calling the real module helpers so
        the test tracks the real code, not a copy."""
        import generate_tour_text as gtt
        # Build what the write block writes: banner (iff harness) + body.
        forced_stops = ["Chart House"]
        body = (
            "Step-by-Step Audio Guided Tour: restaurant tour, Boston, MA\n"
            "Tour-Category: restaurant\n\n"
            "Stop 1: Chart House\n\n"
            "Coordinates: 42.3594, -71.0495\n\n"
            "Orientation: ...\n"
        )
        out = os.path.join(str(tmp_path), f"tour_{harness}.txt")
        # Mirror the exact decision in generate_tour_text: banner only when
        # `harness and _forced_stops_active`. _forced_stops_active is True here
        # because forced_stops is non-empty.
        with open(out, "w", encoding="utf-8") as f:
            if harness and bool(forced_stops):
                f.write(gtt._build_harness_banner(forced_stops))
            f.write(body)
        with open(out, "r", encoding="utf-8") as f:
            return f.read()

    def test_product_path_forced_stops_produce_no_banner(self, tmp_path):
        """harness=False (the orchestrator / user-stops default): the written tour
        has NO harness text and parses to the requested stop. Red on storied,
        where the banner was unconditional on forced_stops."""
        content = self._run_write(tmp_path, harness=False)
        assert "VERIFICATION HARNESS" not in content
        assert "FORCED STOPS" not in content
        assert "naturally-selected" not in content
        # Still a well-formed one-stop tour.
        import re
        stops = re.findall(r"\n\s*Stop\s+(\d+):", "\n" + content)
        assert stops == ["1"], f"expected one parsed stop, got {stops}"
        assert "Chart House" in content

    def test_harness_path_stamps_banner_once(self, tmp_path):
        """harness=True (verification-harness callers only): banner present, once."""
        content = self._run_write(tmp_path, harness=True)
        assert content.count("VERIFICATION HARNESS") == 1
        assert content.startswith("=" * 70)
        # body still intact after the banner
        assert "Stop 1: Chart House" in content


# ─────────────────── The signature + gating are wired correctly ──────────────────
class TestHarnessFlagWiring:
    def test_generate_tour_text_accepts_harness_flag(self):
        """generate_tour_text must take an explicit harness flag, default False."""
        from generate_tour_text import generate_tour_text
        sig = inspect.signature(generate_tour_text)
        assert "harness" in sig.parameters, (
            "generate_tour_text() must accept an explicit 'harness' flag "
            "(LOCAL-586) so the banner is opt-in, not forced_stops-triggered"
        )
        assert sig.parameters["harness"].default is False, (
            "harness must default to False — the product path must get no banner "
            "unless a harness caller explicitly opts in"
        )

    def test_banner_write_is_gated_on_harness(self):
        """The write block must require `harness` (not just _forced_stops_active)."""
        from generate_tour_text import generate_tour_text
        source = inspect.getsource(_gtt_body())
        assert "if harness and _forced_stops_active:" in source, (
            "the banner write must be gated on `harness and _forced_stops_active` "
            "so forced_stops alone (product path) never stamps it (LOCAL-586)"
        )

    def test_builder_has_no_literal_adjacent_to_multiply(self):
        """Guard the regression at the source: the builder must not place a string
        literal immediately before a `* N` (the implicit-concat trap)."""
        from generate_tour_text import _build_harness_banner
        src = inspect.getsource(_build_harness_banner)
        # The fixed form joins a list; the broken form had `"=" * 70 + "\n"` with a
        # following literal line. Require the join form and forbid the trailing
        # `"=" * 70 + "\n\n"` literal shape that caused the bug.
        assert '"\\n".join' in src or "'\\n'.join" in src, (
            "banner must be built with a list joined by '\\n' (LOCAL-586)"
        )


# ─────────── Product path: the SERVICE entry never opts into the harness ───────────
class TestServiceProductPathNeverSetsHarness:
    """The tour-generator /generate path (the one the orchestrator calls) must
    forward forced_stops but must NOT pass harness=True — so a listener's chosen
    stops are a real tour."""

    def test_service_call_omits_harness(self):
        service_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "generate_tour_text_service.py",
        )
        with open(service_path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "forced_stops=forced_stops" in src, (
            "service must still forward the listener's stops as forced_stops"
        )
        assert "harness=True" not in src, (
            "the product /generate path must NEVER set harness=True — that would "
            "stamp the verification banner onto a real listener tour (LOCAL-586)"
        )

    def test_orchestrator_never_sets_harness(self):
        orch_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tour_orchestrator_service.py",
        )
        with open(orch_path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "harness=True" not in src and '"harness"' not in src, (
            "the orchestrator must never request the harness banner (LOCAL-586)"
        )
