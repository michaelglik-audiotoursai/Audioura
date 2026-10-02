"""LOCAL-560 — central model settings for checker vs writer OpenAI calls.

Two knobs, resolved once, used everywhere:

    CHECK_LLM_MODEL   default "gpt-4o-mini"   — verdict / score / list / JSON /
                                                classification / extraction calls
    WRITE_LLM_MODEL   default "gpt-4o"        — prose the listener hears

Why this module exists (LOCAL-560, Michael 2026-10-02): OpenAI is ~$0.28 of a
~$1.00 5-stop tour, and most calls are CHECKS, not writing. `TOUR_LLM_MODEL` was
unset in every environment, so a swathe of call sites silently fell back to
**gpt-3.5-turbo** — older, weaker, and ~3x the price of gpt-4o-mini. This module
replaces those bare fallbacks with one controllable setting per role.

Back-compatibility: each resolver honours the pre-existing site-specific env var
first (e.g. STOP_SPECIFICITY_MODEL), so nothing that already had a knob changes
behaviour. Only when no site-specific override is set does the central default
apply.

Switch policy (from the recording replay, see SUBMISSION_LOCAL-560.md §4):
  * Checker sites proven safe on gpt-4o-mini (100% recall on recorded
    discrepancies, <=10% false alarms) OR extraction checkers that emit no
    reject verdict and produce valid JSON on both models → CHECK_LLM_MODEL.
  * Checker sites that FAILED recall on the recorded set (geography scope gate,
    is-restaurant verify) keep their current model via a per-site default passed
    to check_model(); they are NOT moved onto the cheap default. See
    SUBMISSION §5 for the per-site rationale.
  * Writer sites are not re-pointed to a cheaper model in this task
    (WRITE_LLM_MODEL defaults to gpt-4o); gpt-3.5-turbo writer fallbacks pass
    their current model as the default so their behaviour is unchanged.
"""
import os

CHECK_LLM_MODEL_DEFAULT = "gpt-4o-mini"
WRITE_LLM_MODEL_DEFAULT = "gpt-4o"


def check_model(site_default: str = None, site_env: str = None) -> str:
    """Resolve the model for a CHECKER call site.

    Resolution order:
      1. the site-specific env var (``site_env``), if set — preserves existing
         per-gate knobs (STOP_SPECIFICITY_MODEL, GLOSS_MODEL, ESCALATION_MODEL…).
      2. the central CHECK_LLM_MODEL env var, if set.
      3. ``site_default`` if the caller wants to pin a specific model (used for
         the two gpt-3.5-turbo checker sites that failed recall and must keep
         their current model).
      4. the central default, gpt-4o-mini.
    """
    if site_env:
        v = os.environ.get(site_env)
        if v:
            return v
    v = os.environ.get("CHECK_LLM_MODEL")
    if v:
        return v
    if site_default:
        return site_default
    return CHECK_LLM_MODEL_DEFAULT


def write_model(site_default: str = None, site_env: str = None) -> str:
    """Resolve the model for a WRITER call site.

    Same resolution order as check_model but with the WRITE_LLM_MODEL central
    knob and the gpt-4o default. Writer models are NOT reduced in LOCAL-560, so
    gpt-3.5-turbo writer fallbacks pass site_default="gpt-3.5-turbo" to keep
    today's behaviour when neither env var is set.
    """
    if site_env:
        v = os.environ.get(site_env)
        if v:
            return v
    v = os.environ.get("WRITE_LLM_MODEL")
    if v:
        return v
    if site_default:
        return site_default
    return WRITE_LLM_MODEL_DEFAULT


def held_model(pinned: str, site_env: str = None) -> str:
    """Resolve a CHECKER site that must NOT inherit the central CHECK_LLM_MODEL.

    Used for the two (plus one untested) verdict scope gates that FAILED recall
    on gpt-4o-mini in the recorded replay (is-restaurant verify, geography scope,
    inside-venue scope — SUBMISSION §4/§5). They keep their current model
    (``pinned``, today gpt-3.5-turbo) unless an operator sets their OWN env var
    (``site_env``). The central knob is deliberately bypassed so a global
    CHECK_LLM_MODEL=gpt-4o-mini does not silently degrade them below the
    recall bar Michael's rule requires.
    """
    if site_env:
        v = os.environ.get(site_env)
        if v:
            return v
    return pinned
