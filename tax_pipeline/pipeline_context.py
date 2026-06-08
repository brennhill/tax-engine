"""Per-run pipeline context for in-memory hand-off between rule graph runs.

Background — why this module exists at all:
the 2025 pipeline runs each jurisdiction's rule graph in sequence inside the
same Python process (Germany ordinary, Germany capital, U.S., treaty), and
then the narrative packet builder consumes the executed ``RuleGraphExecution``
objects to render the per-rule audit cards. Re-executing the graphs from the
persisted JSON artifacts loses the fingerprint chain that the audit packets
depend on, so the executions are stashed here and read back later in the same
process.

What changed (item 4 of the audit punch list):
the previous implementation used a module-level mutable dict. Two threads
(or two parallel pipeline runs in the same process) would corrupt each other's
state. The replacement uses ``contextvars.ContextVar``:

- Each thread / asyncio task / explicitly-cleared run sees its own dict.
- The public API (``get_pipeline_context_value``, ``set_pipeline_context_value``,
  ``clear_pipeline_context``) is unchanged so call sites don't need updates.
- Parallel runs no longer collide.

Follow-up (out of scope for the current change-list):
the long-term direction is to eliminate this side channel entirely and thread
the ``RuleGraphExecution`` objects through the call graph as explicit return
values. That refactor must touch ``run_year.py``'s ``runpy.run_module``
orchestration and the narrative-packet builder's signature; it's tracked as
the architectural follow-up to this commit.
"""
from __future__ import annotations

import contextvars
from typing import Any

# A ContextVar holding the per-run dict. Default is None so each fresh
# ContextVar lookup that hasn't yet been written to returns a clean state.
_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "tax_pipeline_run_context",
    default=None,
)


def clear_pipeline_context() -> None:
    """Reset the current context's dict to empty.

    Existing tests call this defensively at the start of each test method so
    that prior runs cannot leak. Under ContextVar this still works: the call
    rebinds ``_CONTEXT`` to a fresh empty dict for the calling context only,
    leaving any sibling thread / task untouched.
    """
    _CONTEXT.set({})


def get_pipeline_context_value(key: str, default: Any = None) -> Any:
    """Read a value from the current context's dict, returning ``default``
    if the key is absent or the context has not been written to yet."""
    current = _CONTEXT.get()
    if current is None:
        return default
    return current.get(key, default)


def set_pipeline_context_value(key: str, value: Any) -> None:
    """Stash a value under ``key`` in the current context's dict.

    Each write rebinds ``_CONTEXT`` to a fresh dict copy that includes the new
    entry. This copy-on-write strategy preserves ContextVar isolation: writes
    in one context (thread, asyncio task, or an explicit
    ``contextvars.copy_context()`` boundary) never leak into a parent or
    sibling context, even though all contexts initially share the same dict
    by inheritance. Without this rebind, the in-place dict mutation would be
    visible to every context that inherited the same dict object.
    """
    current = _CONTEXT.get()
    new = dict(current) if current is not None else {}
    new[key] = value
    _CONTEXT.set(new)
