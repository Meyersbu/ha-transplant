"""Constants for Transplant."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "transplant"
VERSION: Final = "0.1.0"

PANEL_URL: Final = "transplant"
PANEL_TITLE: Final = "Transplant"
PANEL_ICON: Final = "mdi:swap-horizontal-circle"
PANEL_COMPONENT: Final = "transplant-panel"
STATIC_URL: Final = "/transplant_static"
FRONTEND_FILE: Final = "transplant-panel.js"

STORAGE_KEY: Final = "transplant.snapshots"
STORAGE_VERSION: Final = 1
MAX_SNAPSHOTS: Final = 25

PLAN_TTL_SECONDS: Final = 15 * 60
MAX_PLANS: Final = 10
INDEX_MAX_AGE_SECONDS: Final = 120

DEFAULT_DASHBOARD_ID: Final = "lovelace"
