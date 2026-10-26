"""
[LOCAL-771] Red test: no runtime module may still send a retired model.

OpenAI retired ``gpt-3.5-turbo`` (D716). This test fails if any runtime module
on the tour / voice / coordinates paths can still send a retired model name — as
a literal ``"model"`` argument or as a default for a ``model`` parameter — and it
checks that ``llm_fallback.live_model`` rescues retired names while leaving a
live env override untouched.

It is RED on the base (the literals are present) and GREEN after LOCAL-771
rewrites every site through ``llm_fallback``.

Scope note: this scans the runtime modules named in the ticket only. It does NOT
scan ``cost_rates.py`` (keeps its 3.5 *price* rows for old logs), test helpers,
or the ``run_local*`` one-off scripts.
"""
import ast
import os

import pytest

from llm_fallback import (
    RETIRED_MODELS,
    DEFAULT_FALLBACK,
    SCOPE_GATE_FALLBACK,
    live_model,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) \
    if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "tests" \
    else os.path.dirname(os.path.abspath(__file__))

# Every runtime module the ticket lists on the tour / voice / coordinates paths.
RUNTIME_MODULES = [
    "generate_tour_text.py",
    "fact_extractor.py",
    "derepetition_guard.py",
    "directions_generator.py",
    "describe_point_of_interest.py",
    "generate_tour_path.py",
    "tour_hook_generator.py",
    "geocode_stops.py",
    "get_coordinates_openai.py",
    "coordinates_endpoint.py",
    "verify_coordinates_endpoint.py",
    "coordinates_fromAI/app.py",
    "tools/coordinates_direct_tool.py",
    "voice_nlp_service.py",
    "voice_control/app.py",
    "import_tours_to_db.py",
    "add_coordinates_direct.py",
    "add_coordinates_endpoint.py",
    "add_coordinates_to_tour.py",
]


def _docstring_node_ids(tree):
    """Collect id()s of string Constant nodes that are module/class/function
    docstrings, so a retired name merely *mentioned* in prose is not flagged."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


def _flagged_model_in_text(text):
    """Return the retired model name that appears next to a ``model`` key/kwarg
    in ``text`` (a string-literal value), or None.

    Catches both a direct call value (``model="gpt-3.5-turbo"`` / ``"model":
    "gpt-3.5-turbo"``) and the same literal embedded inside a code *template*
    string — the coordinates script-generators build one runtime module as a
    triple-quoted string and write it out, so the retired model must be caught
    there too.
    """
    for retired in RETIRED_MODELS:
        if retired not in text:
            continue
        # Only flag when it reads as a model argument, not loose prose.
        idx = 0
        while True:
            idx = text.find(retired, idx)
            if idx == -1:
                break
            before = text[max(0, idx - 40):idx]
            if "model" in before.lower():
                return retired
            idx += len(retired)
    return None


def _retired_literals(path):
    """Return a list of (lineno, value) for retired-model string literals used
    as a ``model`` argument — directly (dict value / keyword / default) or
    embedded inside a code-template string — excluding docstrings and loose
    prose/comment mentions."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=path)
    doc_ids = _docstring_node_ids(tree)

    # Exclude string Constants that are standalone expression statements
    # (defensive: block comments written as bare strings).
    bare_expr_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            bare_expr_ids.add(id(node.value))

    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in doc_ids or id(node) in bare_expr_ids:
            continue
        val = node.value
        # (a) the whole literal IS a retired model (model="gpt-3.5-turbo")
        if val in RETIRED_MODELS:
            hits.append((node.lineno, val))
            continue
        # (b) a retired model embedded in a larger template string, next to
        #     a model key/kwarg (the script-generator case).
        flagged = _flagged_model_in_text(val)
        if flagged:
            hits.append((node.lineno, flagged))
    return hits


@pytest.mark.parametrize("rel_path", RUNTIME_MODULES)
def test_no_retired_model_literal_in_runtime_module(rel_path):
    path = os.path.join(REPO_ROOT, rel_path)
    if not os.path.exists(path):
        pytest.skip(f"{rel_path} not present in this worktree")
    hits = _retired_literals(path)
    assert not hits, (
        f"{rel_path} still sends a retired model as a code value: "
        + ", ".join(f"line {ln}: {val!r}" for ln, val in hits)
        + ". Route it through llm_fallback.live_model / DEFAULT_FALLBACK "
          "(scope/verify gates: SCOPE_GATE_FALLBACK)."
    )


def test_live_model_maps_retired_to_default():
    assert live_model("gpt-3.5-turbo") == "gpt-4o-mini"
    assert DEFAULT_FALLBACK == "gpt-4o-mini"


def test_live_model_scope_gate_fallback():
    assert live_model("gpt-3.5-turbo", SCOPE_GATE_FALLBACK) == "gpt-4.1-mini"
    assert SCOPE_GATE_FALLBACK == "gpt-4.1-mini"


def test_live_model_passes_through_live_model_names():
    # A real env override must win untouched.
    assert live_model("gpt-4o") == "gpt-4o"
    assert live_model("gpt-4.1-mini") == "gpt-4.1-mini"
    assert live_model("gpt-4o-mini") == "gpt-4o-mini"


def test_live_model_handles_empty():
    assert live_model(None) == "gpt-4o-mini"
    assert live_model("") == "gpt-4o-mini"


def test_env_override_still_wins_through_live_model():
    """TOUR_LLM_MODEL set to a live model must reach the call unchanged; set to a
    retired model it is rescued. This mirrors the runtime pattern
    live_model(os.environ.get("TOUR_LLM_MODEL", DEFAULT_FALLBACK))."""
    saved = os.environ.get("TOUR_LLM_MODEL")
    try:
        os.environ["TOUR_LLM_MODEL"] = "gpt-4o"
        assert live_model(os.environ.get("TOUR_LLM_MODEL", DEFAULT_FALLBACK)) == "gpt-4o"

        os.environ["TOUR_LLM_MODEL"] = "gpt-3.5-turbo"
        assert live_model(os.environ.get("TOUR_LLM_MODEL", DEFAULT_FALLBACK)) == "gpt-4o-mini"

        os.environ.pop("TOUR_LLM_MODEL", None)
        assert live_model(os.environ.get("TOUR_LLM_MODEL", DEFAULT_FALLBACK)) == "gpt-4o-mini"
    finally:
        if saved is None:
            os.environ.pop("TOUR_LLM_MODEL", None)
        else:
            os.environ["TOUR_LLM_MODEL"] = saved


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
