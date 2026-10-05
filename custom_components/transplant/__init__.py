"""Transplant: replace a device in Home Assistant without breaking anything."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    FRONTEND_FILE,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL,
    STATIC_URL,
    VERSION,
)
from .manager import TransplantManager
from .websocket import async_register as async_register_websocket

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_STATIC_REGISTERED = f"{DOMAIN}_static_registered"
_WS_REGISTERED = f"{DOMAIN}_ws_registered"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (UI config entry only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Transplant from a config entry."""
    manager = TransplantManager(hass)
    await manager.async_setup()
    hass.data[DOMAIN] = manager

    # Static files and WebSocket commands cannot be unregistered, so they are
    # registered once per HA run and survive entry reloads.
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL,
                    str(Path(__file__).parent / "frontend"),
                    cache_headers=False,
                )
            ]
        )
        hass.data[_STATIC_REGISTERED] = True
    if not hass.data.get(_WS_REGISTERED):
        async_register_websocket(hass)
        hass.data[_WS_REGISTERED] = True

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        # Version query string busts the browser cache after updates.
        module_url=f"{STATIC_URL}/{FRONTEND_FILE}?v={VERSION}",
        require_admin=True,
        config={"version": VERSION},
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry: remove the panel and listeners."""
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    manager: TransplantManager | None = hass.data.pop(DOMAIN, None)
    if manager is not None:
        manager.async_unload()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete stored undo snapshots when the integration is removed."""
    manager = TransplantManager(hass)
    await manager.async_remove_storage()
