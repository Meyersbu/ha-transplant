"""WebSocket API for the Transplant panel.

Security model:

* Every command requires an authenticated **admin** user. Read commands
  are admin-only too, because they expose raw automation and dashboard
  configuration (which may contain addresses, phone numbers, etc.).
* Read commands (``overview``, ``device_usage``, ``suggest``, ``preview``)
  never change anything. Only ``apply`` and ``undo`` write, and ``apply``
  only accepts a server-side ``plan_id`` produced by ``preview`` — clients
  cannot submit arbitrary configs or file paths.
* WebSocket auth is token based (no cookies), so CSRF does not apply.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .manager import TransplantManager
from .sources import TransplantWriteError

_HEX32 = vol.All(cv.string, vol.Match(r"^[0-9a-f]{32}$"))


def _manager(hass: HomeAssistant) -> TransplantManager | None:
    return hass.data.get(DOMAIN)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register all commands (idempotent per HA run)."""
    for command in (
        ws_overview,
        ws_device_usage,
        ws_suggest,
        ws_preview,
        ws_apply,
        ws_undo,
    ):
        websocket_api.async_register_command(hass, command)


async def _run(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    action: Any,
) -> None:
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Transplant is not set up.")
        return
    try:
        connection.send_result(msg["id"], await action(manager))
    except TransplantWriteError as err:
        connection.send_error(msg["id"], "transplant_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "transplant/overview"})
@websocket_api.async_response
async def ws_overview(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Devices, usage counts, stats and undo history."""
    await _run(hass, connection, msg, lambda m: m.async_overview())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "transplant/device_usage", vol.Required("device_id"): _HEX32}
)
@websocket_api.async_response
async def ws_device_usage(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Everything that uses a device or one of its entities."""
    await _run(hass, connection, msg, lambda m: m.async_device_usage(msg["device_id"]))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "transplant/suggest",
        vol.Required("old_device_id"): _HEX32,
        vol.Required("new_device_id"): _HEX32,
    }
)
@websocket_api.async_response
async def ws_suggest(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Suggested entity mapping between two devices."""

    async def _action(manager: TransplantManager) -> dict[str, Any]:
        return manager.suggest(msg["old_device_id"], msg["new_device_id"])

    await _run(hass, connection, msg, _action)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "transplant/preview",
        vol.Optional("old_device_id"): _HEX32,
        vol.Optional("new_device_id"): _HEX32,
        vol.Required("entity_map"): vol.Schema({cv.entity_id: vol.Any(None, cv.entity_id)}),
    }
)
@websocket_api.async_response
async def ws_preview(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Build a replacement plan (read-only)."""
    await _run(
        hass,
        connection,
        msg,
        lambda m: m.async_preview(
            msg.get("old_device_id"), msg.get("new_device_id"), msg["entity_map"]
        ),
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "transplant/apply", vol.Required("plan_id"): _HEX32}
)
@websocket_api.async_response
async def ws_apply(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Execute a previewed plan."""
    await _run(hass, connection, msg, lambda m: m.async_apply(msg["plan_id"]))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "transplant/undo", vol.Required("snapshot_id"): _HEX32}
)
@websocket_api.async_response
async def ws_undo(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Restore a snapshot."""
    await _run(hass, connection, msg, lambda m: m.async_undo(msg["snapshot_id"]))
