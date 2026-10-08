"""Per-job scoped module state — [LOCAL-631].

Why this exists
---------------
``generate_tour_text_service.py`` runs each tour generation job in its own
``threading.Thread`` inside ONE process. Several modules carried per-job results
in *module-level* mutable globals that the engine wrote during a run and the
service read back AFTER ``generate_tour_text`` returned, e.g.
``generate_tour_text._LAST_GENERATION_COST``, ``_LAST_VENUE_PREFLIGHT``,
``content_qa_runner.FACTUAL_FAIL_COUNT`` and ``story_leads._GROUNDING_REQUESTS``.

A module global is ONE object shared by every thread in the process, so two tours
generated at the same moment overwrote each other's values. Bench R0 caught the
Musée Rodin (tour 498) speaking the Rijksmuseum's (tour 499) hours and admission
price — the preflight/holder state of one job bled into the other.

The cost accumulator (``cost_accumulator.py``) and the dead-host breaker
(``dead_host_breaker.py``) already solved the identical problem with
``contextvars`` scoped per tour. This module generalises that pattern to the
plain "last generation" holders without having to rewrite the hundreds of call
sites that read/mutate them, and without changing any cross-module reader
(the service) or external writer (test runners).

How it works
------------
``contextvars.ContextVar`` values are isolated per :class:`contextvars.Context`.
Crucially, a freshly-spawned ``threading.Thread`` runs with a **fresh** copy of
the context in which the ContextVars hold their *defaults* — a thread does NOT
see values ``set()`` by another thread. Because the service starts each job as a
new ``threading.Thread``, backing these holders with ContextVars gives automatic
per-job isolation: every job thread sees its own default and its own writes, and
can never observe another job's writes.

:class:`JobScopedNamespace` is a single process-wide object whose attribute
access routes to a per-context dict held in one ContextVar. Reading an attribute
returns this job's value (lazily created from a registered factory the first time
it is touched in a context, so mutable defaults like ``{}``/``[]`` are never
shared). Writing an attribute rebinds this job's value only. In-place mutation
(``ns.X.update(...)``, ``ns.X.append(...)``, ``ns.X[k] = v``) mutates this job's
own object, because the getter returns the same per-job instance within a run.

A module wires itself up with :func:`attach_to_module`, which:
  * registers each name + default factory,
  * installs a PEP 562 module ``__getattr__`` so cross-module *reads*
    (``some_module._LAST_X``) resolve to the current job's value, and
  * replaces the module object in ``sys.modules`` with a thin ``ModuleType``
    subclass whose ``__setattr__`` intercepts cross-module *writes*
    (``some_module._LAST_X = v`` done by test runners / orchestrator) so they,
    too, land in the current job's scope rather than a shared global.

Within the owning module, engine code uses the returned namespace object
directly (``_J.LAST_X``) for reads, writes and in-place mutation — all three go
through the ContextVar, so a ``global`` statement (which would bypass any proxy
and write the shared module ``__dict__``) is no longer used for these names.
"""

from __future__ import annotations

import contextvars
import sys
import types
from typing import Any, Callable, Dict, Mapping


class JobScopedNamespace:
    """Attribute namespace whose values are isolated per job (per contextvars
    Context, hence per service job-thread).

    One instance backs all registered names for a single owning module. The
    values live in a single ContextVar holding a ``{name: value}`` dict; the
    ContextVar's default is an empty mapping, so a new context (new job thread)
    starts with no values and each name materialises from its factory on first
    touch.
    """

    __slots__ = ("_var", "_factories", "_name")

    def __init__(self, owner_name: str):
        object.__setattr__(self, "_name", owner_name)
        object.__setattr__(self, "_factories", {})  # type: Dict[str, Callable[[], Any]]
        # Default is an empty dict shared by reference across contexts, but it is
        # NEVER mutated: _store() copies-on-write into the current context the
        # first time this context writes anything. Reads of an unset name return
        # a freshly built factory default without touching the ContextVar, so two
        # contexts can never share a mutable default instance.
        object.__setattr__(
            self, "_var",
            contextvars.ContextVar(f"job_scoped_state::{owner_name}", default={}),
        )

    # -- registration -------------------------------------------------------
    def register(self, name: str, factory: Callable[[], Any]) -> None:
        """Register ``name`` with a zero-arg ``factory`` producing its per-job
        default (e.g. ``dict``, ``list``, ``lambda: 0``, ``lambda: 'full'``)."""
        self._factories[name] = factory

    def registered_names(self):
        return tuple(self._factories.keys())

    # -- per-context storage access ----------------------------------------
    def _current(self) -> Mapping[str, Any]:
        return self._var.get()

    def _store(self, name: str, value: Any) -> None:
        cur = self._var.get()
        # Copy-on-write so one context's writes never mutate the shared default
        # mapping or another context's mapping.
        new = dict(cur)
        new[name] = value
        self._var.set(new)

    def _materialise(self, name: str) -> Any:
        """Return this context's value for ``name``, creating it from the factory
        (and storing it) on first touch so in-place mutation persists."""
        cur = self._var.get()
        if name in cur:
            return cur[name]
        factory = self._factories.get(name)
        value = factory() if factory is not None else None
        self._store(name, value)
        return value

    # -- attribute protocol -------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        # __slots__ names and dunders never reach here. Registered names resolve
        # to the per-job value; anything else is a genuine attribute error.
        factories = object.__getattribute__(self, "_factories")
        if name in factories:
            return object.__getattribute__(self, "_materialise")(name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        factories = object.__getattribute__(self, "_factories")
        if name in factories:
            object.__getattribute__(self, "_store")(name, value)
            return
        # Allow setting unknown names too (defensive): treat as a job-scoped var
        # so a late-registered name still isolates rather than silently sharing.
        object.__getattribute__(self, "_store")(name, value)

    def reset(self) -> None:
        """Clear ALL job-scoped values for the current context, restoring each
        registered name to a fresh factory default on next touch. Call at the
        start of a job to guarantee a clean slate even if the same thread/context
        is reused (e.g. a worker pool or a test re-using the main thread)."""
        self._var.set({})


class _ScopedModule(types.ModuleType):
    """A ``ModuleType`` subclass that routes cross-module reads/writes of the
    registered per-job names to the module's :class:`JobScopedNamespace`.

    ``module.NAME`` read  -> namespace value for the current job (via __getattr__,
                             only consulted because NAME is absent from __dict__).
    ``module.NAME = v`` write -> namespace.NAME = v (intercepted here; a plain
                             module would store v in the shared __dict__).
    """

    def __getattr__(self, name: str) -> Any:  # only when missing from __dict__
        ns = self.__dict__.get("_JOB_SCOPED_NS")
        if ns is not None and name in ns.registered_names():
            return getattr(ns, name)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        ns = self.__dict__.get("_JOB_SCOPED_NS")
        if ns is not None and name in ns.registered_names():
            setattr(ns, name, value)
            return
        object.__setattr__(self, name, value)


def attach_to_module(module_name: str,
                     specs: Mapping[str, Callable[[], Any]]) -> JobScopedNamespace:
    """Wire per-job scoping into the module named ``module_name``.

    ``specs`` maps each per-job name to a zero-arg default factory. Returns the
    :class:`JobScopedNamespace` the module should use internally for those names.

    Side effects on the module:
      * ensures the registered names are NOT present as plain module globals
        (so PEP 562 ``__getattr__`` is consulted for cross-module reads);
      * installs/extends a module ``__getattr__`` delegating to the namespace;
      * reclasses the module object to :class:`_ScopedModule` so cross-module
        writes are intercepted.

    Idempotent per module: a second call extends the registration set.
    """
    module = sys.modules[module_name]

    ns = module.__dict__.get("_JOB_SCOPED_NS")
    if not isinstance(ns, JobScopedNamespace):
        ns = JobScopedNamespace(module_name)
        # Stash on the module BEFORE reclassing so _ScopedModule can find it.
        module.__dict__["_JOB_SCOPED_NS"] = ns

    for name, factory in specs.items():
        ns.register(name, factory)
        # Remove any plain global so cross-module reads fall through to
        # __getattr__ and internal `global NAME` reinitialisation can't resurrect
        # a shared value. (Internal code uses the namespace object directly.)
        module.__dict__.pop(name, None)

    # Install a PEP 562 module __getattr__ that delegates to the namespace,
    # chaining to any pre-existing module __getattr__.
    _existing = module.__dict__.get("__getattr__")
    if getattr(_existing, "_job_scoped_installed", False):
        _existing = getattr(_existing, "_prev", None)

    def __getattr__(name, _ns=ns, _prev=_existing):  # module-level PEP 562 hook
        if name in _ns.registered_names():
            return getattr(_ns, name)
        if _prev is not None:
            return _prev(name)
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")

    __getattr__._job_scoped_installed = True  # type: ignore[attr-defined]
    __getattr__._prev = _existing  # type: ignore[attr-defined]
    module.__dict__["__getattr__"] = __getattr__

    # Reclass the module so cross-module writes are intercepted. Safe: we only
    # change the type; the __dict__ (and thus all other attributes) is preserved.
    if not isinstance(module, _ScopedModule):
        module.__class__ = _ScopedModule

    return ns
