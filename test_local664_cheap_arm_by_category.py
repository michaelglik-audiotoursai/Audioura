"""test_local664_cheap_arm_by_category.py — [LOCAL-664] D645 follow-up.

Proves CHEAP_ARM_CATEGORIES gates NARRATION_MODEL / NARRATION_PROVIDER /
RESEARCH_BACKEND by the tour's category, with no cross-contamination between two
concurrent tours of different categories.

  * museum   → mini + serper  (cheap arm ON)
  * walking  → production defaults (cheap arm OFF)
  * unset    → the envs apply to EVERY category (today's behaviour)
  * two concurrent tours of different categories do not cross-contaminate

Uses only fakes — no network, no paid calls.
"""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import cheap_arm
import story_leads
import generate_tour_text as gtt


class _EnvGuard:
    """Context manager that restores the three controlled envs + the gate env."""

    KEYS = ("CHEAP_ARM_CATEGORIES", "NARRATION_MODEL", "NARRATION_PROVIDER",
            "RESEARCH_BACKEND")

    def __init__(self, **values):
        self._values = values

    def __enter__(self):
        self._saved = {k: os.environ.get(k) for k in self.KEYS}
        for k in self.KEYS:
            os.environ.pop(k, None)
        for k, v in self._values.items():
            if v is not None:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def _route_for(category):
    """Bind the category then read both decisions, as a worker would see them."""
    token = cheap_arm.set_tour_category(category)
    try:
        return gtt.narration_model_route(), story_leads.research_backend()
    finally:
        cheap_arm.reset_tour_category(token)


class CheapArmByCategory(unittest.TestCase):

    # ── 1. museum → mini + serper when the gate names museum ──────────────────
    def test_museum_gets_mini_and_serper(self):
        with _EnvGuard(CHEAP_ARM_CATEGORIES="museum",
                       NARRATION_PROVIDER="openai",
                       NARRATION_MODEL="gpt-4.1-mini",
                       RESEARCH_BACKEND="serper"):
            (provider, model), backend = _route_for("museum")
            self.assertEqual(provider, "openai")
            self.assertEqual(model, "gpt-4.1-mini")
            self.assertEqual(backend, "serper")
            self.assertTrue(cheap_arm.cheap_arm_active("museum"))

    # ── 2. walking → production defaults when the gate names only museum ──────
    def test_walking_gets_production_defaults(self):
        with _EnvGuard(CHEAP_ARM_CATEGORIES="museum",
                       NARRATION_PROVIDER="gemini",
                       NARRATION_MODEL="gpt-4.1-mini",
                       RESEARCH_BACKEND="serper"):
            (provider, model), backend = _route_for("walking")
            # Env ignored for walking: production narration = openai + story_pass_model.
            self.assertEqual(provider, "openai")
            self.assertEqual(model, gtt.story_pass_model())
            self.assertEqual(backend, "gemini")
            self.assertFalse(cheap_arm.cheap_arm_active("walking"))

    # ── 3. gate UNSET → the envs apply to EVERY category (today's behaviour) ──
    def test_unset_env_applies_everywhere(self):
        with _EnvGuard(NARRATION_PROVIDER="gemini",
                       NARRATION_MODEL="gpt-4.1-mini",
                       RESEARCH_BACKEND="serper"):
            self.assertFalse(cheap_arm.gate_active())
            for cat in ("museum", "walking", "restaurant", "facility", ""):
                (provider, model), backend = _route_for(cat)
                self.assertEqual((provider, model), ("gemini", "gpt-4.1-mini"),
                                 f"narration env must apply for {cat!r} when gate unset")
                self.assertEqual(backend, "serper",
                                 f"research env must apply for {cat!r} when gate unset")

    # ── 3b. gate SET but no controlled envs → defaults everywhere ─────────────
    def test_gate_set_without_envs_is_defaults(self):
        with _EnvGuard(CHEAP_ARM_CATEGORIES="museum"):
            (provider, model), backend = _route_for("museum")
            self.assertEqual(provider, "openai")
            self.assertEqual(model, gtt.story_pass_model())
            self.assertEqual(backend, "gemini")

    # ── 4. two concurrent tours of different categories do not cross-contaminate
    def test_concurrent_tours_do_not_cross_contaminate(self):
        """A museum tour and a walking tour run at the same time; each worker must
        read ITS OWN category's routing. The ThreadPoolExecutor.submit contextvar
        patch (cost_accumulator) copies the per-tour category into the worker, so
        we drive the two tours through two executors that each set the category on
        their own thread — the real fan-out shape."""
        with _EnvGuard(CHEAP_ARM_CATEGORIES="museum",
                       NARRATION_PROVIDER="openai",
                       NARRATION_MODEL="gpt-4.1-mini",
                       RESEARCH_BACKEND="serper"):

            start = threading.Barrier(2)
            results = {}

            def _tour(category):
                # Each tour binds its category on its own thread (as the generator
                # does at tour start), then fans a worker out and reads routing
                # inside the worker to prove isolation under concurrency.
                token = cheap_arm.set_tour_category(category)
                try:
                    start.wait(timeout=5)

                    def _worker():
                        return (gtt.narration_model_route(),
                                story_leads.research_backend(),
                                cheap_arm.tour_category())

                    with ThreadPoolExecutor(max_workers=1) as ex:
                        results[category] = ex.submit(_worker).result(timeout=5)
                finally:
                    cheap_arm.reset_tour_category(token)

            t_museum = threading.Thread(target=_tour, args=("museum",))
            t_walking = threading.Thread(target=_tour, args=("walking",))
            t_museum.start()
            t_walking.start()
            t_museum.join(timeout=10)
            t_walking.join(timeout=10)

            (m_route, m_backend, m_cat) = results["museum"]
            (w_route, w_backend, w_cat) = results["walking"]

            # Museum worker: cheap arm ON.
            self.assertEqual(m_cat, "museum")
            self.assertEqual(m_route, ("openai", "gpt-4.1-mini"))
            self.assertEqual(m_backend, "serper")

            # Walking worker: cheap arm OFF — production defaults, uncontaminated by
            # the museum tour running at the same instant.
            self.assertEqual(w_cat, "walking")
            self.assertEqual(w_route, ("openai", gtt.story_pass_model()))
            self.assertEqual(w_backend, "gemini")

    # ── 5. contextvar propagates into a pool worker via the cost_accumulator patch
    def test_contextvar_propagates_into_pool_worker(self):
        import cost_accumulator
        cost_accumulator.install_executor_context_propagation()
        try:
            with _EnvGuard(CHEAP_ARM_CATEGORIES="museum",
                           NARRATION_PROVIDER="openai",
                           NARRATION_MODEL="gpt-4.1-mini",
                           RESEARCH_BACKEND="serper"):
                token = cheap_arm.set_tour_category("museum")
                try:
                    def _worker():
                        return (cheap_arm.tour_category(),
                                gtt.narration_model_route(),
                                story_leads.research_backend())

                    with ThreadPoolExecutor(max_workers=2) as ex:
                        cat, route, backend = ex.submit(_worker).result(timeout=5)
                    self.assertEqual(cat, "museum")
                    self.assertEqual(route, ("openai", "gpt-4.1-mini"))
                    self.assertEqual(backend, "serper")
                finally:
                    cheap_arm.reset_tour_category(token)
        finally:
            cost_accumulator.uninstall_executor_context_propagation()

    # ── 6. explicit propagation helper for raw pools ─────────────────────────
    def test_run_in_category_context_helper(self):
        with _EnvGuard(CHEAP_ARM_CATEGORIES="museum",
                       NARRATION_MODEL="gpt-4.1-mini",
                       RESEARCH_BACKEND="serper"):
            cheap_arm.set_tour_category("walking")  # the "parent" tour
            cat = "museum"

            def _worker():
                return cheap_arm.tour_category(), story_leads.research_backend()

            # A raw thread does NOT inherit the contextvar; the helper re-binds it.
            out = {}

            def _run():
                out["v"] = cheap_arm.run_in_category_context(cat, _worker)

            t = threading.Thread(target=_run)
            t.start()
            t.join(timeout=5)
            self.assertEqual(out["v"], ("museum", "serper"))

    # ── 7. log line shape (step 3) ───────────────────────────────────────────
    def test_log_decision_shape(self):
        lines = []
        with _EnvGuard(CHEAP_ARM_CATEGORIES="museum",
                       NARRATION_MODEL="gpt-4.1-mini",
                       RESEARCH_BACKEND="serper"):
            on = cheap_arm.log_decision("museum", printer=lines.append)
            off = cheap_arm.log_decision("walking", printer=lines.append)
        self.assertIn("[LOCAL-664] cheap arm: ON for category=museum", on)
        self.assertIn("[LOCAL-664] cheap arm: OFF for category=walking", off)
        self.assertEqual(len(lines), 2)

    # ── 8. category parsing edge cases ───────────────────────────────────────
    def test_category_parsing(self):
        with _EnvGuard(CHEAP_ARM_CATEGORIES=" Museum , Facility ,, museum "):
            self.assertEqual(cheap_arm.cheap_arm_categories(), ["museum", "facility"])
            self.assertTrue(cheap_arm.gate_active())
        with _EnvGuard(CHEAP_ARM_CATEGORIES=" , ,"):
            self.assertFalse(cheap_arm.gate_active())
            self.assertEqual(cheap_arm.cheap_arm_categories(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
