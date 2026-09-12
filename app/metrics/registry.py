"""Module registry. Decorate a class with @register and it appears in the UI."""

from __future__ import annotations

from typing import Any

_MODULES: dict[str, Any] = {}


class DuplicateModuleError(RuntimeError):
    pass


def register(cls):
    """Class decorator: instantiate the module once and add it to the registry."""
    module_id = getattr(cls, "id", None)
    if not module_id:
        raise ValueError(f"{cls.__name__} must define a unique `id`")
    if module_id in _MODULES:
        raise DuplicateModuleError(
            f"Metric module id '{module_id}' is already registered by "
            f"{type(_MODULES[module_id]).__name__}"
        )
    _MODULES[module_id] = cls()
    return cls


def all_modules() -> list[Any]:
    return sorted(_MODULES.values(), key=lambda m: (getattr(m, "order", 100), m.name))


def get_module(module_id: str):
    return _MODULES.get(module_id)


def descriptors() -> list[dict[str, Any]]:
    """What the frontend needs to lay out one card per module and know which tab
    it belongs to. `tabs` defaults to ("summary", "team") — most modules render on
    both the comparison view and each team's own page, scoped via SeriesContext's
    team_filter; a module opts into "matches" (or out of "team") by declaring its
    own `tabs` class attribute, as match_results does.
    """
    return [
        {
            "id": m.id,
            "name": m.name,
            "description": getattr(m, "description", ""),
            "order": getattr(m, "order", 100),
            "tabs": list(getattr(m, "tabs", ("summary", "team"))),
        }
        for m in all_modules()
    ]
