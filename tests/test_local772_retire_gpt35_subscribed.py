"""
[LOCAL-772] Red test: on the `subscribed` tree no runtime module may still
RESOLVE to a retired model (D716 — OpenAI retired ``gpt-3.5-turbo``).

Subscribed differs from storied (LOCAL-771): the tour / voice / coordinates call
sites here route their model through the LOCAL-560 resolvers in ``llm_models.py``
(``check_model`` / ``write_model`` / ``held_model``). A bare literal
``site_default="gpt-3.5-turbo"`` or ``held_model("gpt-3.5-turbo", ...)`` is
therefore *not* a bug by itself — it is a documented historical pin that the
resolver now maps to a live model. So this test has two halves:

  1. RESOLVER UNIT TEST — with every model env var UNSET, no resolver call form
     actually used at a runtime site may return a retired model. This is the
     real contract and the part that was RED before LOCAL-772 routed the
     resolvers through ``live_model`` (``held_model`` used to return the pinned
     ``gpt-3.5-turbo`` verbatim). It also asserts an env override still wins and
     a stale env override naming a retired model is rescued.

  2. AST SCAN — scan the runtime modules for a retired model used DIRECTLY as a
     ``model`` argument (dict value / keyword / default / code-template string),
     i.e. a site that bypasses the resolvers and would 404. Literals that are an
     argument to one of the ``llm_models`` resolvers are exempt, because the
     resolver rescues them (half 1 proves that). This is RED on a tree where any
     such bare site survives and GREEN once every bare site is rewritten.

Scope note: scans the runtime modules named in the ticket only. It does NOT scan
``cost_rates.py`` / ``cost_meter.py`` / ``cost_accumulator.py`` /
``reconcile_paid_api.py`` / ``translation-service/*`` / ``_meter/*`` (they keep
their 3.5 *price* rows for old logs), test helpers, the ``run_local*`` one-off
scripts, or ``modified_generate_tour_text.py`` (its service is not wired into
compose or any Dockerfile — see SUBMISSION_LOCAL-772.md).
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
import llm_models

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) \
    if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "tests" \
    else os.path.dirname(os.path.abspath(__file__))

# The llm_models resolvers that rescue a retired model-name argument. A retired
# literal passed to one of these is NOT a bug (the resolver maps it live).
RESOLVER_NAMES = {
    "check_model", "_check_model",
    "write_model", "_write_model",
    "held_model", "_held_model",
}

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
    "tools/coordinates_test_tool.py",
    "voice_nlp_service.py",
    "voice_control/app.py",
    "import_tours_to_db.py",
    "add_coordinates_direct.py",
    "add_coordinates_endpoint.py",
    "add_coordinates_to_tour.py",
]


# ───────────────────────── 1. RESOLVER UNIT TEST ─────────────────────────

# The exact resolver call forms used at the runtime sites (grepped from the
# tree): every one must resolve to a live model with all env vars unset.
_RESOLVER_CALL_FORMS = [
    ("check_model()", lambda: llm_models.check_model()),
    ("write_model()", lambda: llm_models.write_model()),
    ('write_model(site_default="gpt-3.5-turbo")',
        lambda: llm_models.write_model(site_default="gpt-3.5-turbo")),
    ('held_model("gpt-3.5-turbo", site_env="IS_RESTAURANT_MODEL")',
        lambda: llm_models.held_model("gpt-3.5-turbo", site_env="IS_RESTAURANT_MODEL")),
    ('held_model("gpt-3.5-turbo", site_env="GEO_SCOPE_MODEL")',
        lambda: llm_models.held_model("gpt-3.5-turbo", site_env="GEO_SCOPE_MODEL")),
    ('held_model("gpt-3.5-turbo", site_env="VENUE_SCOPE_MODEL")',
        lambda: llm_models.held_model("gpt-3.5-turbo", site_env="VENUE_SCOPE_MODEL")),
    ("check_model(site_env='GLOSS_TRIAGE_MODEL')",
        lambda: llm_models.check_model(site_env="GLOSS_TRIAGE_MODEL")),
    ("check_model(site_env='ESCALATION_MODEL')",
        lambda: llm_models.check_model(site_env="ESCALATION_MODEL")),
]

_MODEL_ENV_VARS = (
    "CHECK_LLM_MODEL", "WRITE_LLM_MODEL", "TOUR_LLM_MODEL",
    "IS_RESTAURANT_MODEL", "GEO_SCOPE_MODEL", "VENUE_SCOPE_MODEL",
    "GLOSS_TRIAGE_MODEL", "ESCALATION_MODEL",
)


@pytest.fixture
def clean_model_env():
    saved = {k: os.environ.get(k) for k in _MODEL_ENV_VARS}
    for k in _MODEL_ENV_VARS:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.mark.parametrize("label,call", _RESOLVER_CALL_FORMS,
                         ids=[lbl for lbl, _ in _RESOLVER_CALL_FORMS])
def test_resolver_never_resolves_to_retired_model(label, call, clean_model_env):
    """With env unset, no runtime resolver call form returns a retired model."""
    resolved = call()
    assert resolved not in RETIRED_MODELS, (
        f"{label} resolved to retired model {resolved!r} with env unset. "
        "Route the resolver result through llm_fallback.live_model "
        "(checker/writer -> DEFAULT_FALLBACK, scope/verify gates -> "
        "SCOPE_GATE_FALLBACK)."
    )


def test_held_model_maps_retired_pin_to_scope_gate(clean_model_env):
    """The three recall-pinned checkers (is-restaurant / geo-scope / venue-scope)
    must land on gpt-4.1-mini (D716), not the retired pin, not the cheap
    checker default."""
    for env in ("IS_RESTAURANT_MODEL", "GEO_SCOPE_MODEL", "VENUE_SCOPE_MODEL"):
        assert llm_models.held_model("gpt-3.5-turbo", site_env=env) == SCOPE_GATE_FALLBACK


def test_write_model_site_default_maps_to_default(clean_model_env):
    assert llm_models.write_model(site_default="gpt-3.5-turbo") == DEFAULT_FALLBACK


def test_live_env_override_still_wins_through_resolvers(clean_model_env):
    os.environ["WRITE_LLM_MODEL"] = "gpt-4o"
    assert llm_models.write_model(site_default="gpt-3.5-turbo") == "gpt-4o"
    os.environ["IS_RESTAURANT_MODEL"] = "gpt-4o"
    assert llm_models.held_model("gpt-3.5-turbo", site_env="IS_RESTAURANT_MODEL") == "gpt-4o"


def test_stale_retired_env_override_is_rescued(clean_model_env):
    """An operator env var still naming the retired model is mapped live, not
    passed through to 404."""
    os.environ["WRITE_LLM_MODEL"] = "gpt-3.5-turbo"
    assert llm_models.write_model() == DEFAULT_FALLBACK
    os.environ["GEO_SCOPE_MODEL"] = "gpt-3.5-turbo"
    assert llm_models.held_model("gpt-3.5-turbo", site_env="GEO_SCOPE_MODEL") == SCOPE_GATE_FALLBACK


# ───────────────────────── 2. AST SCAN ─────────────────────────

def _docstring_node_ids(tree):
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


def _resolver_arg_ids(tree):
    """id()s of string Constants that are arguments to an llm_models resolver
    call (positional or keyword). Those are rescued by the resolver, so a
    retired literal there is not a live-call bug."""
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name not in RESOLVER_NAMES:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                ids.add(id(arg))
        for kw in node.keywords:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                ids.add(id(kw.value))
    return ids


def _flagged_model_in_text(text):
    for retired in RETIRED_MODELS:
        if retired not in text:
            continue
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
    """(lineno, value) for retired-model string literals used DIRECTLY as a
    model argument, excluding docstrings, bare block-comment strings, and
    literals handed to an llm_models resolver (which rescues them)."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=path)
    doc_ids = _docstring_node_ids(tree)
    resolver_ids = _resolver_arg_ids(tree)

    bare_expr_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            bare_expr_ids.add(id(node.value))

    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in doc_ids or id(node) in bare_expr_ids or id(node) in resolver_ids:
            continue
        val = node.value
        if val in RETIRED_MODELS:
            hits.append((node.lineno, val))
            continue
        flagged = _flagged_model_in_text(val)
        if flagged:
            hits.append((node.lineno, flagged))
    return hits


@pytest.mark.parametrize("rel_path", RUNTIME_MODULES)
def test_no_bare_retired_model_literal_in_runtime_module(rel_path):
    path = os.path.join(REPO_ROOT, rel_path)
    if not os.path.exists(path):
        pytest.skip(f"{rel_path} not present in this worktree")
    hits = _retired_literals(path)
    assert not hits, (
        f"{rel_path} sends a retired model as a bare code value (not via an "
        f"llm_models resolver): "
        + ", ".join(f"line {ln}: {val!r}" for ln, val in hits)
        + ". Route it through llm_fallback.live_model / DEFAULT_FALLBACK "
          "(scope/verify gates: SCOPE_GATE_FALLBACK), or through the "
          "llm_models resolvers."
    )


# ───────────────────────── live_model primitives ─────────────────────────

def test_live_model_maps_retired_to_default():
    assert live_model("gpt-3.5-turbo") == "gpt-4o-mini"
    assert DEFAULT_FALLBACK == "gpt-4o-mini"


def test_live_model_scope_gate_fallback():
    assert live_model("gpt-3.5-turbo", SCOPE_GATE_FALLBACK) == "gpt-4.1-mini"
    assert SCOPE_GATE_FALLBACK == "gpt-4.1-mini"


def test_live_model_passes_through_live_names():
    assert live_model("gpt-4o") == "gpt-4o"
    assert live_model("gpt-4.1-mini") == "gpt-4.1-mini"
    assert live_model("gpt-4o-mini") == "gpt-4o-mini"


def test_live_model_handles_empty():
    assert live_model(None) == "gpt-4o-mini"
    assert live_model("") == "gpt-4o-mini"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
