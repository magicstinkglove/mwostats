"""Auto-discover metric modules.

Every .py file in this package is imported at startup, so dropping a new module file in
here registers it — no edits to this file, the routes, or the frontend.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import MetricModule, SeriesContext  # noqa: F401  (re-exported for modules)
from .registry import all_modules, descriptors, get_module, register  # noqa: F401

_SKIP = {"base", "registry"}


def load_modules() -> None:
    package_dir = Path(__file__).parent
    for info in pkgutil.iter_modules([str(package_dir)]):
        if info.name in _SKIP or info.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{info.name}")


load_modules()
