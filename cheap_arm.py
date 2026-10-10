"""cheap_arm.py — [LOCAL-664] per-category "cheap arm" env gating (D645 follow-up).

Why this exists
---------------
D645 measured that ``NARRATION_MODEL=gpt-4.1-mini`` + ``RESEARCH_BACKEND=serper``
cut a 3-stop museum tour from ≈ $0.50 to ≈ $0.30 at equal Kiro quality, but on a
Boston WALKING request it scored one point lower (6.5 → 5.5). LEAD wants the cheap
arm ON for museum tours ONLY.

Rather than teach every call site a different rule, this module introduces ONE
env, ``CHEAP_ARM_CATEGORIES`` (a comma list, e.g. ``museum`` or ``museum,facility``),
and ONE helper, :func:`effective_env`, that every cheap-arm-controlled env read
goes through. The three controlled envs are:

    NARRATION_MODEL, NARRATION_PROVIDER, RESEARCH_BACKEND

Semantics
---------
* ``CHEAP_ARM_CATEGORIES`` UNSET  → today's behaviour EXACTLY. The controlled
  envs apply to every tour, whatever its category. :func:`effective_env` returns
  the raw ``os.environ`` value (or the caller's ``default`` when unset), so the
  call sites behave byte-for-byte as before this change.
* ``CHEAP_ARM_CATEGORIES`` SET    → the controlled envs apply ONLY when the
  current tour's category (the same ``tour_category`` that writes
  ``Tour-Category:``) is in the list. For a tour whose category is NOT in the
  list, :func:`effective_env` IGNORES the env and returns the production default
  (the caller's ``default``), so that tour runs on the production models/backend.

Category propagation
---------------------
The current tour's category must be known at every call site, including the
per-stop story pass that fans out across ``ThreadPoolExecutor`` workers. The
category is held in a module-level :class:`contextvars.ContextVar`, set ONCE on
the tour's own thread at generation start (right where ``tour_category`` becomes
final) via :func:`set_tour_category`.

``ThreadPoolExecutor`` does NOT copy contextvars into its workers by default, but
``cost_accumulator.install_executor_context_propagation()`` (installed at import
of ``generate_tour_text``) patches ``ThreadPoolExecutor.submit`` to run every
submitted callable inside ``contextvars.copy_context()`` — which copies THIS
ContextVar along with the cost scope. So a worker started inside a tour sees that
tour's category automatically, exactly as LOCAL-651 / LOCAL-656 rely on for their
own per-tour scopes. For pools or raw threads that bypass that patch,
:func:`run_in_category_context` / :func:`copy_category_context` re-bind the value
explicitly (same shape as ``dead_host_breaker.run_in_tour_context``). No module
global is used for the category, so two concurrent tours of different categories
never cross-contaminate.
"""

from __future__ import annotations

import contextvars
import os
from typing import List, Optional

# The three envs whose effect is gated by CHEAP_ARM_CATEGORIES. Reads of these,
# on the tour path, go through effective_env() so they only apply to in-list
# categories when the gate is active.
CHEAP_ARM_CATEGORIES_ENV = "CHEAP_ARM_CATEGORIES"
CONTROLLED_ENVS = ("NARRATION_MODEL", "NARRATION_PROVIDER", "RESEARCH_BACKEND")

# Per-tour category. Default "" means "unknown / not set"; with the gate active an
# unknown category is treated as NOT in the list (production defaults), which is the
# safe choice — a tour whose category we could not determine must not silently get
# the cheaper, lower-quality arm.
_tour_category: "contextvars.ContextVar[str]" = contextvars.ContextVar(
    "cheap_arm::tour_category", default=""
)


# ── category contextvar ──────────────────────────────────────────────────────
def set_tour_category(category: Optional[str]) -> "contextvars.Token":
    """Bind the current tour's category for this context. Returns the Token so a
    caller may ``reset_tour_category`` it; the tour path sets it once at start and
    lets the context expire with the request thread."""
    return _tour_category.set((category or "").strip().lower())


def reset_tour_category(token: "contextvars.Token") -> None:
    """Restore the category ContextVar to its prior value (pairs with the token
    returned by :func:`set_tour_category`)."""
    try:
        _tour_category.reset(token)
    except (ValueError, LookupError):  # pragma: no cover - token from another context
        pass


def tour_category() -> str:
    """The current tour's category (lowercased), or '' when none is set."""
    return _tour_category.get()


# ── env parsing ──────────────────────────────────────────────────────────────
def _is_set(raw: Optional[str]) -> bool:
    """A CHEAP_ARM_CATEGORIES value counts as SET only when it names at least one
    non-empty category. An unset var, '', or a string of only commas/space is
    treated as UNSET so the gate stays off (today's behaviour)."""
    return bool(raw and raw.strip() and _parse_categories(raw))


def _parse_categories(raw: Optional[str]) -> List[str]:
    """Parse a comma list into lowercased, stripped, de-duplicated categories
    (order preserved)."""
    out: List[str] = []
    for part in (raw or "").split(","):
        c = part.strip().lower()
        if c and c not in out:
            out.append(c)
    return out


def cheap_arm_categories() -> List[str]:
    """The configured cheap-arm categories, [] when the gate is unset/empty."""
    return _parse_categories(os.environ.get(CHEAP_ARM_CATEGORIES_ENV, ""))


def gate_active() -> bool:
    """True when CHEAP_ARM_CATEGORIES is set to at least one category — i.e. the
    controlled envs are category-gated rather than global."""
    return _is_set(os.environ.get(CHEAP_ARM_CATEGORIES_ENV, ""))


def cheap_arm_active(category: Optional[str] = None) -> bool:
    """Whether the cheap arm applies to this tour.

    * Gate UNSET → True (the controlled envs apply to EVERYTHING, as today).
    * Gate SET   → True only when ``category`` (default: the current contextvar
      category) is in the configured list.
    """
    if not gate_active():
        return True
    cat = (category if category is not None else tour_category()) or ""
    return cat.strip().lower() in cheap_arm_categories()


# ── the one hook every controlled env read uses ──────────────────────────────
def effective_env(name: str, default: Optional[str] = None,
                  category: Optional[str] = None) -> Optional[str]:
    """Return the effective value of a cheap-arm-controlled env for this tour.

    * Gate UNSET → ``os.environ.get(name, default)`` (byte-for-byte today).
    * Gate SET and this tour's category IS in the list → the raw env value
      (``os.environ.get(name, default)``) — the cheap arm applies.
    * Gate SET and this tour's category is NOT in the list → ``default`` (the
      production default); the env is ignored for this tour.

    ``name`` should be one of :data:`CONTROLLED_ENVS`.
    """
    if cheap_arm_active(category):
        return os.environ.get(name, default)
    # Gate active but this category is excluded: pretend the env is unset so the
    # caller falls back to its production default.
    return default


# ── per-tour log line ────────────────────────────────────────────────────────
def log_decision(category: Optional[str] = None, *, printer=print) -> str:
    """Build and emit the once-per-tour decision line (step 3 of LOCAL-664):

        [LOCAL-664] cheap arm: ON|OFF for category=<c> (models: …)

    Returns the line so callers/tests can assert on it. ``printer`` is injectable
    for tests; it defaults to the builtin ``print`` the rest of the generator uses.
    """
    cat = (category if category is not None else tour_category()) or ""
    on = cheap_arm_active(cat)
    if gate_active():
        narration_model = effective_env("NARRATION_MODEL", "", cat) or "(default)"
        narration_provider = effective_env("NARRATION_PROVIDER", "", cat) or "(default)"
        research_backend = effective_env("RESEARCH_BACKEND", "", cat) or "(default)"
        models = (f"NARRATION_PROVIDER={narration_provider}, "
                  f"NARRATION_MODEL={narration_model}, "
                  f"RESEARCH_BACKEND={research_backend}")
        gate = f"categories={cheap_arm_categories()}"
    else:
        # Gate unset: the controlled envs apply to everything exactly as before.
        models = "gate unset — controlled envs apply to all tours"
        gate = "categories=UNSET"
    line = (f"[LOCAL-664] cheap arm: {'ON' if on else 'OFF'} for "
            f"category={cat or '(unknown)'} ({gate}; {models})")
    try:
        printer(line)
    except Exception:  # pragma: no cover - logging must never break generation
        pass
    return line


# ── explicit pool / thread propagation (belt-and-braces) ─────────────────────
def copy_category_context() -> str:
    """Capture the active tour's category for propagation to worker threads.

    Mirrors ``dead_host_breaker.copy_tour_context``. Normally unnecessary because
    ``cost_accumulator.install_executor_context_propagation`` already copies the
    whole context (this ContextVar included) into ThreadPoolExecutor workers; use
    this for a raw pool/thread that bypasses that patch.
    """
    return tour_category()


def run_in_category_context(category: str, fn, *args, **kwargs):
    """Run ``fn(*args, **kwargs)`` with ``category`` re-bound as the current tour
    category. Helper for thread-pool submissions that do not inherit context:

        cat = copy_category_context()
        executor.submit(run_in_category_context, cat, worker, arg)
    """
    token = set_tour_category(category)
    try:
        return fn(*args, **kwargs)
    finally:
        reset_tour_category(token)
