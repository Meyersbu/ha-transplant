"""End-to-end tests against a real Home Assistant core.

Run with ``pytest tests/integration`` after installing
``requirements_test.txt``. Covers the full MVP workflow:
setup → overview → usage → suggest → preview → apply → verify → undo → unload.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import yaml

DOMAIN = "transplant"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom_components/transplant."""


def _write_yaml(hass: HomeAssistant, name: str, data: Any) -> None:
    Path(hass.config.path(name)).write_text(yaml.safe_dump(data, sort_keys=False))


def _read_yaml(hass: HomeAssistant, name: str) -> Any:
    return yaml.safe_load(Path(hass.config.path(name)).read_text())


@pytest.fixture
async def env(hass: HomeAssistant, hass_storage: dict[str, Any]) -> dict[str, Any]:
    """An instance with a dead old sensor, a new sensor, and config using it."""
    other_entry = MockConfigEntry(domain="zha", title="ZHA")
    other_entry.add_to_hass(hass)
    new_entry = MockConfigEntry(domain="mqtt", title="MQTT")
    new_entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    old_dev = dev_reg.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("zha", "old")},
        name="Hallway sensor (old)",
        manufacturer="Aqara",
        model="WSDCGQ11LM",
    )
    new_dev = dev_reg.async_get_or_create(
        config_entry_id=new_entry.entry_id,
        identifiers={("mqtt", "new")},
        name="Hallway sensor",
        manufacturer="Sonoff",
        model="SNZB-02D",
    )
    old_temp = ent_reg.async_get_or_create(
        "sensor",
        "zha",
        "old_t",
        device_id=old_dev.id,
        config_entry=other_entry,
        original_device_class="temperature",
        unit_of_measurement="°C",
        suggested_object_id="hallway_temperature",
    )
    old_hum = ent_reg.async_get_or_create(
        "sensor",
        "zha",
        "old_h",
        device_id=old_dev.id,
        config_entry=other_entry,
        original_device_class="humidity",
        unit_of_measurement="%",
        suggested_object_id="hallway_humidity",
    )
    new_temp = ent_reg.async_get_or_create(
        "sensor",
        "mqtt",
        "new_t",
        device_id=new_dev.id,
        config_entry=new_entry,
        original_device_class="temperature",
        unit_of_measurement="°C",
        suggested_object_id="sonoff_temperature",
    )
    new_hum = ent_reg.async_get_or_create(
        "sensor",
        "mqtt",
        "new_h",
        device_id=new_dev.id,
        config_entry=new_entry,
        original_device_class="humidity",
        unit_of_measurement="%",
        suggested_object_id="sonoff_humidity",
    )
    hass.states.async_set(old_temp.entity_id, STATE_UNAVAILABLE)
    hass.states.async_set(old_hum.entity_id, STATE_UNAVAILABLE)
    hass.states.async_set(new_temp.entity_id, "21.5", {"unit_of_measurement": "°C"})
    hass.states.async_set(new_hum.entity_id, "48", {"unit_of_measurement": "%"})

    _write_yaml(
        hass,
        "automations.yaml",
        [
            {
                "id": "1001",
                "alias": "Hallway too warm",
                "triggers": [
                    {"trigger": "numeric_state", "entity_id": old_temp.entity_id, "above": 25}
                ],
                "conditions": [
                    {
                        "condition": "template",
                        "value_template": f"{{{{ states('{old_hum.entity_id}') | float(0) > 40 }}}}",
                    }
                ],
                "actions": [
                    {
                        "action": "input_boolean.turn_on",
                        "target": {"entity_id": "input_boolean.fan"},
                    }
                ],
            },
            {
                "id": "1002",
                "alias": "Button pressed (ZHA device trigger)",
                "triggers": [
                    {
                        "trigger": "device",
                        "device_id": old_dev.id,
                        "domain": "zha",
                        "type": "remote_button_short_press",
                        "subtype": "turn_on",
                    }
                ],
                "actions": [
                    {"action": "input_boolean.toggle", "target": {"entity_id": "input_boolean.fan"}}
                ],
            },
            {
                "id": "1003",
                "alias": "Unrelated",
                "triggers": [{"trigger": "state", "entity_id": "input_boolean.fan"}],
                "actions": [],
            },
        ],
    )
    _write_yaml(
        hass,
        "scripts.yaml",
        {
            "report": {
                "alias": "Report",
                "sequence": [
                    {
                        "action": "persistent_notification.create",
                        "data": {"message": f"{{{{ states('{old_temp.entity_id}') }}}}"},
                    }
                ],
            }
        },
    )
    _write_yaml(hass, "scenes.yaml", [])

    hass_storage["lovelace"] = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace",
        "data": {
            "config": {
                "views": [
                    {
                        "title": "Home",
                        "cards": [
                            {"type": "tile", "entity": old_temp.entity_id},
                            {
                                "type": "entities",
                                "entities": [old_hum.entity_id, "input_boolean.fan"],
                            },
                        ],
                    }
                ]
            }
        },
    }

    Path(hass.config.path("configuration.yaml")).write_text(  # noqa: ASYNC240
        "automation: !include automations.yaml\n"
        "script: !include scripts.yaml\n"
        "scene: !include scenes.yaml\n"
    )
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"fan": None}})
    assert await async_setup_component(hass, "automation", {})
    assert await async_setup_component(hass, "script", {})
    # Reload reads configuration.yaml, exactly like a real instance.
    await hass.services.async_call("automation", "reload", blocking=True)
    await hass.services.async_call("script", "reload", blocking=True)
    assert await async_setup_component(hass, "lovelace", {})

    entry = MockConfigEntry(domain=DOMAIN, title="Transplant")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return {
        "entry": entry,
        "old_dev": old_dev,
        "new_dev": new_dev,
        "old_temp": old_temp.entity_id,
        "old_hum": old_hum.entity_id,
        "new_temp": new_temp.entity_id,
        "new_hum": new_hum.entity_id,
    }


async def _ws(client: Any, **msg: Any) -> dict[str, Any]:
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def test_full_workflow(
    hass: HomeAssistant, hass_ws_client: Any, hass_storage: dict[str, Any], env: dict[str, Any]
) -> None:
    """Overview → usage → suggest → preview → apply → undo."""
    client = await hass_ws_client(hass)

    overview = await _ws(client, type="transplant/overview")
    assert overview["success"], overview
    old = next(d for d in overview["result"]["devices"] if d["id"] == env["old_dev"].id)
    assert old["unavailable"] is True
    assert old["used_in"] == 4  # 2 automations, 1 script, 1 dashboard

    usage = await _ws(client, type="transplant/device_usage", device_id=env["old_dev"].id)
    assert {i["source_type"] for i in usage["result"]["items"]} == {
        "automation",
        "script",
        "dashboard",
    }

    suggest = await _ws(
        client,
        type="transplant/suggest",
        old_device_id=env["old_dev"].id,
        new_device_id=env["new_dev"].id,
    )
    mapping = {m["old_entity_id"]: m["new_entity_id"] for m in suggest["result"]["matches"]}
    assert mapping == {env["old_temp"]: env["new_temp"], env["old_hum"]: env["new_hum"]}

    preview = await _ws(
        client,
        type="transplant/preview",
        old_device_id=env["old_dev"].id,
        new_device_id=env["new_dev"].id,
        entity_map=mapping,
    )
    assert preview["success"], preview
    summary = preview["result"]["summary"]
    assert summary["objects"] == 3  # automation 1001, script, dashboard
    assert summary["replacements"] == 5
    assert summary["needs_review"] == 1  # ZHA device trigger → MQTT device

    # Preview must not change anything.
    assert _read_yaml(hass, "automations.yaml")[0]["triggers"][0]["entity_id"] == env["old_temp"]

    applied = await _ws(client, type="transplant/apply", plan_id=preview["result"]["plan_id"])
    assert applied["success"], applied
    assert applied["result"]["replacements"] == 5
    assert applied["result"]["verification"]["ok"], applied["result"]["verification"]

    autos = _read_yaml(hass, "automations.yaml")
    assert autos[0]["triggers"][0]["entity_id"] == env["new_temp"]
    assert env["new_hum"] in autos[0]["conditions"][0]["value_template"]
    assert autos[1]["triggers"][0]["device_id"] == env["old_dev"].id  # left for review
    assert (
        env["new_temp"]
        in _read_yaml(hass, "scripts.yaml")["report"]["sequence"][0]["data"]["message"]
    )
    await hass.async_block_till_done()
    dash = hass_storage["lovelace"]["data"]["config"]
    assert dash["views"][0]["cards"][0]["entity"] == env["new_temp"]
    assert dash["views"][0]["cards"][1]["entities"][0] == env["new_hum"]

    # The same plan cannot be applied twice.
    again = await _ws(client, type="transplant/apply", plan_id=preview["result"]["plan_id"])
    assert not again["success"]

    undo = await _ws(client, type="transplant/undo", snapshot_id=applied["result"]["snapshot_id"])
    assert undo["success"], undo
    assert undo["result"]["restored"] == 3 and undo["result"]["conflicts"] == []
    assert _read_yaml(hass, "automations.yaml")[0]["triggers"][0]["entity_id"] == env["old_temp"]


async def test_stale_preview_is_rejected(
    hass: HomeAssistant, hass_ws_client: Any, env: dict[str, Any]
) -> None:
    """Editing an object after the preview aborts the apply."""
    client = await hass_ws_client(hass)
    preview = await _ws(
        client, type="transplant/preview", entity_map={env["old_temp"]: env["new_temp"]}
    )
    autos = _read_yaml(hass, "automations.yaml")
    autos[0]["alias"] = "Edited meanwhile"
    _write_yaml(hass, "automations.yaml", autos)
    applied = await _ws(client, type="transplant/apply", plan_id=preview["result"]["plan_id"])
    assert not applied["success"]
    assert "changed since the preview" in applied["error"]["message"]


async def test_non_admin_is_rejected(
    hass: HomeAssistant, hass_ws_client: Any, hass_read_only_access_token: str, env: dict[str, Any]
) -> None:
    """All commands are admin-only."""
    client = await hass_ws_client(hass, hass_read_only_access_token)
    result = await _ws(client, type="transplant/overview")
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"


async def test_unload_and_reload(hass: HomeAssistant, env: dict[str, Any]) -> None:
    """Entry unloads cleanly and can be set up again."""
    entry = env["entry"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert "transplant" not in hass.data.get("frontend_panels", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED


async def test_config_flow_single_instance(hass: HomeAssistant) -> None:
    """User step creates one entry; a second attempt aborts."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "abort"


async def test_panel_assets_are_served(
    hass: HomeAssistant, hass_client: Any, env: dict[str, Any]
) -> None:
    """The panel module and its imports are served from the static path."""
    client = await hass_client()
    for name in ("transplant-panel.js", "api.js", "dom.js", "styles.js"):
        response = await client.get(f"/transplant_static/{name}")
        assert response.status == 200, name
    panels = hass.data["frontend_panels"]
    assert panels["transplant"].require_admin is True


async def test_remove_entry_deletes_snapshots(
    hass: HomeAssistant, hass_ws_client: Any, hass_storage: dict[str, Any], env: dict[str, Any]
) -> None:
    """Removing the integration removes the panel and its stored snapshots."""
    client = await hass_ws_client(hass)
    preview = await _ws(
        client, type="transplant/preview", entity_map={env["old_temp"]: env["new_temp"]}
    )
    applied = await _ws(client, type="transplant/apply", plan_id=preview["result"]["plan_id"])
    assert applied["success"]
    await hass.async_block_till_done()
    assert "transplant.snapshots" in hass_storage
    assert await hass.config_entries.async_remove(env["entry"].entry_id)
    await hass.async_block_till_done()
    assert "transplant.snapshots" not in hass_storage
    assert "transplant" not in hass.data.get("frontend_panels", {})
