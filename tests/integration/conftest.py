"""Integration tests need the Home Assistant test harness."""

from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

import custom_components

# The harness ships its own ``custom_components`` package for HA's own tests,
# which shadows ours. Make our integration discoverable alongside it.
_OURS = str(Path(__file__).parents[2] / "custom_components")
if _OURS not in custom_components.__path__:
    custom_components.__path__.insert(0, _OURS)
