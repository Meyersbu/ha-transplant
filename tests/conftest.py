"""Test configuration.

The analysis engine in ``custom_components/transplant/core`` has no Home
Assistant dependency. We load it as a standalone package so the core test
suite runs in milliseconds without installing Home Assistant.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

TESTS_DIR = Path(__file__).parent
CORE_DIR = TESTS_DIR.parent / "custom_components" / "transplant" / "core"


def _load_core() -> None:
    spec = importlib.util.spec_from_file_location(
        "transplant_core",
        CORE_DIR / "__init__.py",
        submodule_search_locations=[str(CORE_DIR)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["transplant_core"] = module
    spec.loader.exec_module(module)


_load_core()
sys.path.insert(0, str(TESTS_DIR))
