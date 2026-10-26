"""
[LOCAL-771] Retired-model fallback (D716).

OpenAI retired ``gpt-3.5-turbo`` on 2026-10-26: a chat call with that model now
returns ``The model 'gpt-3.5-turbo' has been deprecated`` (HTTP 404). Every
runtime site on the tour / voice / coordinates paths used to default to
``gpt-3.5-turbo`` (``TOUR_LLM_MODEL`` is unset everywhere), so each one quietly
failed — fact sheets 0/N, style retries 404, every scope/verify gate failing
open and passing everything through. See DECISIONS D716.

Ruling (D716, LEAD):
  * Every runtime call that would have sent ``gpt-3.5-turbo`` sends
    ``gpt-4o-mini`` instead (``DEFAULT_FALLBACK``). It is cheaper than 3.5 and
    stronger; LOCAL-560 already measured it on the checker sites.
  * Exception — the two checker sites LOCAL-560 kept OFF 4o-mini because recall
    dropped (the geography/venue scope gate and the is-restaurant verify) go to
    ``gpt-4.1-mini`` (``SCOPE_GATE_FALLBACK``, the narration model already in
    use).
  * Any env override (``TOUR_LLM_MODEL`` or a site-specific ``*_MODEL``) still
    wins; only the *fallback* changes. ``live_model`` is applied on top of an
    override so that an env var still pointing at a retired model is also
    rescued.

This module is deliberately tiny and dependency-free so every runtime file can
import it without pulling in the tour pipeline.
"""

# Models OpenAI has retired. A runtime call must never send one of these.
# Extend this set as further models are retired.
RETIRED_MODELS = {
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0301",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-16k-0613",
    "gpt-3.5-turbo-instruct",
}

# What a retired model falls back to everywhere by default.
DEFAULT_FALLBACK = "gpt-4o-mini"

# The two LOCAL-560 checker sites (geography/venue scope gate, is-restaurant
# verify) that lost recall on 4o-mini keep the stronger narration-tier model.
SCOPE_GATE_FALLBACK = "gpt-4.1-mini"


def live_model(name, fallback=DEFAULT_FALLBACK):
    """Map a (possibly retired) model name to a model OpenAI still serves.

    If ``name`` is a retired model (e.g. ``gpt-3.5-turbo``) — or is empty/None —
    return ``fallback`` (``gpt-4o-mini`` by default; pass
    ``SCOPE_GATE_FALLBACK`` for the scope/verify gates). Any live model name is
    returned unchanged, so a genuine env override still wins.

    >>> live_model("gpt-3.5-turbo")
    'gpt-4o-mini'
    >>> live_model("gpt-3.5-turbo", SCOPE_GATE_FALLBACK)
    'gpt-4.1-mini'
    >>> live_model("gpt-4o")
    'gpt-4o'
    """
    if not name:
        return fallback
    if name in RETIRED_MODELS:
        return fallback
    return name


if __name__ == "__main__":  # tiny self-check
    assert live_model("gpt-3.5-turbo") == "gpt-4o-mini"
    assert live_model("gpt-3.5-turbo", SCOPE_GATE_FALLBACK) == "gpt-4.1-mini"
    assert live_model("gpt-4o") == "gpt-4o"
    assert live_model(None) == "gpt-4o-mini"
    assert live_model("") == "gpt-4o-mini"
    print("llm_fallback self-check OK")
