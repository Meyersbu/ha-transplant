"""Tests for replacement logic, plan building and entity matching."""

from __future__ import annotations

import copy
import time

from fixtures import make_installation
import pytest

from transplant_core import (
    ConfigSource,
    EntityInfo,
    KnownIds,
    ReferenceIndex,
    Replacements,
    SourceType,
    TargetType,
    build_plan,
    fingerprint,
    plan_item,
    suggest_entity_mapping,
)

OLD_DEV, NEW_DEV = "1" * 32, "2" * 32
OLD_REG, NEW_REG = "3" * 32, "4" * 32

REPL = Replacements(
    entities={"sensor.old_temp": "sensor.new_temp", "light.lamp": "light.lamp_new"},
    devices={OLD_DEV: NEW_DEV},
    entity_registry_ids={OLD_REG: NEW_REG},
    old_integration="zha",
    new_integration="zha",
)


def _source(config: object, editable: bool = True) -> ConfigSource:
    return ConfigSource(SourceType.AUTOMATION, "a", "A", config, editable)


def test_replaces_values_keys_and_templates_without_mutating_input() -> None:
    config = {
        "triggers": [{"trigger": "numeric_state", "entity_id": "sensor.old_temp", "above": 25}],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{{ states('sensor.old_temp') | float > states.sensor.old_temp_2.state | float }}",
            }
        ],
        "actions": [
            {"action": "light.turn_on", "target": {"entity_id": ["light.lamp", "light.other"]}},
            {"scene": {"entities": {"light.lamp": "on"}}},
        ],
    }
    original = copy.deepcopy(config)
    item = plan_item(_source(config), REPL)

    assert config == original  # pure
    updated = item.updated_config
    assert updated["triggers"][0]["entity_id"] == "sensor.new_temp"
    # Only the exact token is replaced, not sensor.old_temp_2
    assert updated["conditions"][0]["value_template"] == (
        "{{ states('sensor.new_temp') | float > states.sensor.old_temp_2.state | float }}"
    )
    assert updated["actions"][0]["target"]["entity_id"] == ["light.lamp_new", "light.other"]
    assert updated["actions"][1]["scene"]["entities"] == {"light.lamp_new": "on"}
    assert len(item.changes) == 4


def test_device_blocks_same_integration_are_rewritten() -> None:
    config = {
        "triggers": [
            {
                "trigger": "device",
                "device_id": OLD_DEV,
                "domain": "zha",
                "type": "remote_button_short_press",
                "subtype": "turn_on",
            }
        ],
        "actions": [
            {"device_id": OLD_DEV, "domain": "light", "entity_id": OLD_REG, "type": "turn_on"}
        ],
    }
    item = plan_item(_source(config), REPL)
    assert item.updated_config["triggers"][0]["device_id"] == NEW_DEV
    assert item.updated_config["actions"][0]["entity_id"] == NEW_REG
    assert item.review == []


def test_integration_specific_device_trigger_is_flagged_across_integrations() -> None:
    repl = Replacements(
        devices={OLD_DEV: NEW_DEV},
        entity_registry_ids={OLD_REG: NEW_REG},
        old_integration="zha",
        new_integration="mqtt",
    )
    config = {
        "triggers": [
            {
                "trigger": "device",
                "device_id": OLD_DEV,
                "domain": "zha",
                "type": "remote_button_short_press",
            }
        ],
        # Entity-domain device action is portable and still rewritten.
        "actions": [
            {"device_id": OLD_DEV, "domain": "light", "entity_id": OLD_REG, "type": "turn_on"}
        ],
    }
    item = plan_item(_source(config), repl)
    assert item.updated_config["triggers"][0]["device_id"] == OLD_DEV
    assert len(item.review) == 1 and item.review[0].path == "triggers[0]"
    assert item.updated_config["actions"][0]["device_id"] == NEW_DEV


def test_scene_key_collision_is_not_merged() -> None:
    config = {"entities": {"light.lamp": "on", "light.lamp_new": "off"}}
    item = plan_item(_source(config), REPL)
    assert item.updated_config == config
    assert len(item.review) == 1


def test_comma_separated_string() -> None:
    item = plan_item(_source({"entity_id": "light.lamp, light.other"}), REPL)
    assert item.updated_config["entity_id"] == "light.lamp_new, light.other"


def test_build_plan_only_touches_affected_sources_and_finds_removed_ids() -> None:
    # sensor.old_temp is no longer known (device died) – it must still be found.
    known = KnownIds(entities={"sensor.new_temp", "light.unrelated"})
    known.extra_entities |= set(REPL.entities)
    sources = [
        _source({"entity_id": "sensor.old_temp"}),
        ConfigSource(SourceType.DASHBOARD, "d", "D", {"entity": "light.unrelated"}, True),
        ConfigSource(
            SourceType.SCRIPT, "s", "S", {"entity_id": "light.lamp"}, False, read_only_reason="yaml"
        ),
    ]
    index = ReferenceIndex.build(sources, known)
    plan = build_plan(sources, index, REPL)
    summary = plan.summary()
    assert summary["objects"] == 1
    assert summary["replacements"] == 1
    assert summary["read_only"] == 1
    assert set(plan.fingerprints) == {(SourceType.AUTOMATION, "a"), (SourceType.SCRIPT, "s")}


def test_fingerprint_detects_changes_and_ignores_key_order() -> None:
    assert fingerprint({"a": 1, "b": [1, 2]}) == fingerprint({"b": [1, 2], "a": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


def _info(entity_id: str, **kw) -> EntityInfo:
    return EntityInfo(
        entity_id=entity_id, registry_id=entity_id, domain=entity_id.split(".", maxsplit=1)[0], **kw
    )


def test_entity_matching_prefers_device_class_and_unit() -> None:
    old = [
        _info("sensor.hall_temperature", device_class="temperature", unit="°C"),
        _info("sensor.hall_humidity", device_class="humidity", unit="%"),
        _info(
            "sensor.hall_battery", device_class="battery", unit="%", entity_category="diagnostic"
        ),
        _info("binary_sensor.hall_motion", device_class="motion"),
    ]
    new = [
        _info(
            "sensor.sonoff_battery", device_class="battery", unit="%", entity_category="diagnostic"
        ),
        _info("sensor.sonoff_humidity", device_class="humidity", unit="%"),
        _info("sensor.sonoff_temperature", device_class="temperature", unit="°C"),
    ]
    result = {m.old_entity_id: m for m in suggest_entity_mapping(old, new)}
    assert result["sensor.hall_temperature"].new_entity_id == "sensor.sonoff_temperature"
    assert result["sensor.hall_humidity"].new_entity_id == "sensor.sonoff_humidity"
    assert result["sensor.hall_battery"].new_entity_id == "sensor.sonoff_battery"
    assert result["sensor.hall_temperature"].confidence == "high"
    assert result["binary_sensor.hall_motion"].new_entity_id is None
    assert result["binary_sensor.hall_motion"].confidence == "none"


@pytest.mark.parametrize(
    ("entities", "devices", "automations", "dashboards", "budget_s"),
    [(50, 10, 20, 2, 0.5), (500, 100, 100, 5, 1.0), (5000, 600, 600, 25, 4.0)],
)
def test_performance_index_and_plan(entities, devices, automations, dashboards, budget_s) -> None:
    inst = make_installation(entities, devices, automations, dashboards)
    start = time.perf_counter()
    index = ReferenceIndex.build(inst.sources, inst.known)
    target = inst.entity_ids[7]
    plan = build_plan(inst.sources, index, Replacements(entities={target: target + "_new"}))
    elapsed = time.perf_counter() - start
    assert elapsed < budget_s, f"{elapsed:.2f}s for {entities} entities"
    usage = index.usage_count(TargetType.ENTITY, target)
    assert plan.summary()["objects"] == usage
