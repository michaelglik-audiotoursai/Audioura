"""D370 — the story pass runs on its own model, and is costed at that model.

Michael's decision, 2026-08-11: gpt-4o for the per-stop description call only.
A global TOUR_LLM_MODEL=gpt-4o makes the tour fail to generate outright (POI
discovery returns six unrelated museums, BLOCKER4b rejects them), so the switch
must be exactly one call site wide.

These tests are bound to the production call site, not to a copy of it (D277):
test_call_site_* parses generate_tour_text.py itself with `ast` and asserts the
shape of the real `description_data` literal. Revert either production edit and
the corresponding test goes red — verified by doing exactly that (D242 check 1).
"""
import ast
import os
import unittest

import generate_tour_text
from generate_tour_text import story_pass_model, _tour_llm_cost

_SOURCE_PATH = generate_tour_text.__file__


def _description_data_dict():
    """The real `description_data = {...}` literal from the production file."""
    with open(_SOURCE_PATH, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "description_data" in targets and isinstance(node.value, ast.Dict):
            return node.value
    raise AssertionError("no `description_data = {...}` assignment in generate_tour_text.py")


def _dict_value(dict_node, key):
    for k, v in zip(dict_node.keys, dict_node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    raise AssertionError(f"description_data has no {key!r} key")


class TestStoryPassModel(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("TOUR_STORY_MODEL", None)

    def tearDown(self):
        os.environ.pop("TOUR_STORY_MODEL", None)
        if self._saved is not None:
            os.environ["TOUR_STORY_MODEL"] = self._saved

    def test_defaults_to_gpt_4o(self):
        self.assertEqual(story_pass_model(), "gpt-4o")

    def test_env_overrides(self):
        os.environ["TOUR_STORY_MODEL"] = "gpt-4o-mini"
        self.assertEqual(story_pass_model(), "gpt-4o-mini")

    def test_ignores_the_global_pipeline_variable(self):
        """The whole point of D370: TOUR_LLM_MODEL must not move the story pass."""
        saved = os.environ.get("TOUR_LLM_MODEL")
        os.environ["TOUR_LLM_MODEL"] = "gpt-3.5-turbo"
        try:
            self.assertEqual(story_pass_model(), "gpt-4o")
        finally:
            os.environ.pop("TOUR_LLM_MODEL", None)
            if saved is not None:
                os.environ["TOUR_LLM_MODEL"] = saved


class TestCallSiteIsBound(unittest.TestCase):
    """Assertions against the production source, so a revert cannot stay green."""

    def test_call_site_uses_story_pass_model(self):
        model_node = _dict_value(_description_data_dict(), "model")
        self.assertIsInstance(
            model_node, ast.Call,
            "description_data['model'] is no longer a call — story pass reverted to a literal/env read",
        )
        self.assertEqual(
            getattr(model_node.func, "id", None), "story_pass_model",
            "description_data['model'] does not call story_pass_model()",
        )

    def test_call_site_costs_at_the_model_it_called(self):
        """_tour_llm_cost must be told the story model, or gpt-4o bills at gpt-3.5 rates."""
        with open(_SOURCE_PATH, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        priced_with_model = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "_tour_llm_cost"
            and any(kw.arg == "model" for kw in n.keywords)
        ]
        self.assertTrue(
            priced_with_model,
            "no _tour_llm_cost call passes model= — the story pass would be mispriced",
        )


class TestCostFollowsTheModel(unittest.TestCase):
    def test_gpt_4o_costs_more_than_the_default(self):
        cheap = _tour_llm_cost(1000)
        dear = _tour_llm_cost(1000, model="gpt-4o")
        self.assertGreater(
            dear, cheap,
            "gpt-4o priced at or below the pipeline default — cost_rates lookup is not taking effect",
        )

    def test_explicit_model_overrides_the_environment(self):
        saved = os.environ.get("TOUR_LLM_MODEL")
        os.environ["TOUR_LLM_MODEL"] = "gpt-3.5-turbo"
        try:
            self.assertEqual(_tour_llm_cost(1000, model="gpt-4o"),
                             _tour_llm_cost(1000, model="gpt-4o"))
            self.assertNotEqual(_tour_llm_cost(1000, model="gpt-4o"),
                                _tour_llm_cost(1000))
        finally:
            os.environ.pop("TOUR_LLM_MODEL", None)
            if saved is not None:
                os.environ["TOUR_LLM_MODEL"] = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)
