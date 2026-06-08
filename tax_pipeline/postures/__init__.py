"""Filing-posture registry — Proposal 2 jurisdiction-driven shape.

Pre-P2 the registry imported ``germany.py`` and ``usa.py`` at module
load and built ``_POSTURE_REGISTRY`` from named symbols. P2 inverts
that: the canonical list of jurisdictions lives in
:data:`tax_pipeline.jurisdictions.JURISDICTION_REGISTRY`, and this
module iterates that registry, lazy-importing each jurisdiction's
posture submodule on first access.

The public API of :func:`get_posture_definition` /
:func:`known_postures` is unchanged. Adding a third jurisdiction
(UK, FR, ...) means adding one row to the jurisdiction registry plus
its ``postures/<key>/`` package — no edit here.

I13 (disabled-jurisdiction explicit absence) is unaffected: posture
lookup happens before any I13 gate consults
``elections.<jurisdiction>_filing_required``.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from tax_pipeline.jurisdictions import JURISDICTION_REGISTRY
from tax_pipeline.postures.base import OutputSurfaceSupport, PostureDefinition


# Cache of posture-package modules. Lazy: only imported on first
# ``get_posture_definition`` / ``known_postures`` call.
_POSTURE_PACKAGE_CACHE: dict[str, ModuleType] = {}


def _load_posture_package(registry_key: str) -> ModuleType:
    """Import the ``tax_pipeline.postures.<registry_key>`` package once.

    The registry-driven lookup uses ``posture_registry_key`` (the
    historical lowercase name "germany", "usa") because the
    on-disk package layout still uses those names. The ISO-2 code
    is the registry key but does NOT correspond to a directory.
    """
    if registry_key in _POSTURE_PACKAGE_CACHE:
        return _POSTURE_PACKAGE_CACHE[registry_key]
    # Look up via the jurisdiction registry to fail closed on unknown
    # jurisdiction names (rather than hard-coding "germany"/"usa").
    matched = None
    for definition in JURISDICTION_REGISTRY.values():
        if definition.posture_registry_key == registry_key:
            matched = definition
            break
    if matched is None:
        raise ValueError(
            f"No jurisdiction registered for posture key {registry_key!r}. "
            f"Known keys: {sorted(d.posture_registry_key for d in JURISDICTION_REGISTRY.values())}"
        )
    package = importlib.import_module(matched.posture_module)
    _POSTURE_PACKAGE_CACHE[registry_key] = package
    return package


def _build_registry() -> dict[tuple[str, str], PostureDefinition]:
    """Walk every registered jurisdiction and collect its postures.

    Each posture-package ``__init__.py`` re-exports the per-posture
    ``DEFINITION`` symbols (e.g. ``SINGLE``, ``MARRIED_JOINT``); we
    consume ``__all__`` if present, otherwise every uppercase name on
    the package object whose value is a :class:`PostureDefinition`.
    """
    registry: dict[tuple[str, str], PostureDefinition] = {}
    for definition in JURISDICTION_REGISTRY.values():
        registry_key = definition.posture_registry_key
        package = _load_posture_package(registry_key)
        names = getattr(package, "__all__", None)
        if names is None:
            names = [n for n in dir(package) if n.isupper() and not n.startswith("_")]
        for name in names:
            obj = getattr(package, name, None)
            if isinstance(obj, PostureDefinition):
                registry[(registry_key, obj.filing_posture)] = obj
    return registry


# The registry is built eagerly at module load to preserve the
# pre-P2 behaviour where ``get_posture_definition`` had no first-call
# import latency. Lazy-importing per jurisdiction is an optimisation
# for jurisdictions that are never referenced; with two jurisdictions
# both touched on every run, eager construction has the same cost.
_POSTURE_REGISTRY: dict[tuple[str, str], PostureDefinition] = _build_registry()


def get_posture_definition(jurisdiction: str, filing_posture: str) -> PostureDefinition:
    normalized = (jurisdiction.strip().lower(), filing_posture.strip().lower())
    if normalized not in _POSTURE_REGISTRY:
        raise ValueError(
            f"Unsupported filing posture {filing_posture!r} for jurisdiction {jurisdiction!r}."
        )
    return _POSTURE_REGISTRY[normalized]


def known_postures(jurisdiction: str) -> dict[str, str]:
    normalized = jurisdiction.strip().lower()
    return {
        posture: definition.module_path
        for (registered_jurisdiction, posture), definition in _POSTURE_REGISTRY.items()
        if registered_jurisdiction == normalized
    }


__all__ = ["OutputSurfaceSupport", "PostureDefinition", "get_posture_definition", "known_postures"]
