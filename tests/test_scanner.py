"""Tests for the reference scanner."""

from __future__ import annotations

from transplant_core import (
    ConfigSource,
    KnownIds,
    MatchKind,
    ReferenceIndex,
    SourceType,
    TargetType,
    scan_source,
)

DEV_OLD = "a" * 32
REG_OLD = "b" * 32

KNOWN = KnownIds(
    entities={"light.kitchen", "light.kitchen_2", "sensor.hall_temp", "binary_sensor.door"},
    devices={DEV_OLD},
    registry_ids={REG_OLD: "light.kitchen"},
)


def _scan(config: object, source_type: SourceType = SourceType.AUTOMATION):
    source = ConfigSource(source_type, "x", "X", config, True)
    return scan_source(source, KNOWN.matcher())


def _targets(refs):
    return sorted((r.target_type.value, r.target_id, r.kind.value) for r in refs)


def test_finds_values_in_nested_actions_and_lists() -> None:
    refs = _scan(
        {
            "triggers": [{"trigger": "state", "entity_id": ["binary_sensor.door"]}],
            "actions": [
                {
                    "choose": [
                        {
                            "sequence": [
                                {
                                    "action": "light.turn_on",
                                    "target": {"entity_id": "light.kitchen"},
                                }
                            ]
                        }
                    ]
                }
            ],
        }
    )
    assert _targets(refs) == [
        ("entity", "binary_sensor.door", "value"),
        ("entity", "light.kitchen", "value"),
    ]
    paths = {r.path for r in refs}
    assert "actions[0].choose[0].sequence[0].target.entity_id" in paths


def test_service_names_and_unknown_ids_are_not_references() -> None:
    # light.turn_on looks like an entity id but is not a known entity.
    refs = _scan({"action": "light.turn_on", "target": {"entity_id": "light.ghost"}})
    assert refs == []


def test_template_tokens_do_not_match_prefixes() -> None:
    refs = _scan(
        {
            "value_template": "{{ is_state('light.kitchen_2', 'on') and states.sensor.hall_temp.state | float > 3 }}"
        }
    )
    assert _targets(refs) == [
        ("entity", "light.kitchen_2", "template"),
        ("entity", "sensor.hall_temp", "template"),
    ]


def test_device_and_registry_ids() -> None:
    refs = _scan(
        {
            "triggers": [
                {
                    "trigger": "device",
                    "device_id": DEV_OLD,
                    "domain": "light",
                    "entity_id": REG_OLD,
                    "type": "turned_on",
                }
            ],
            "conditions": [
                {
                    "condition": "template",
                    "value_template": f"{{{{ device_attr('{DEV_OLD}', 'name') }}}}",
                }
            ],
        }
    )
    assert _targets(refs) == [
        ("device", DEV_OLD, "template"),
        ("device", DEV_OLD, "value"),
        ("entity_registry_id", REG_OLD, "value"),
    ]


def test_scene_entity_keys() -> None:
    refs = _scan({"id": "1", "entities": {"light.kitchen": {"state": "on"}}}, SourceType.SCENE)
    assert len(refs) == 1
    assert refs[0].kind is MatchKind.KEY
    assert refs[0].path == "entities[light.kitchen]"


def test_comma_separated_legacy_entity_ids() -> None:
    refs = _scan({"entity_id": "light.kitchen, binary_sensor.door"})
    assert {r.target_id for r in refs} == {"light.kitchen", "binary_sensor.door"}


def test_dashboard_custom_card_arbitrary_keys() -> None:
    refs = _scan(
        {
            "views": [
                {
                    "cards": [
                        {
                            "type": "custom:mushroom-template-card",
                            "secondary_entity_whatever": "sensor.hall_temp",
                        }
                    ]
                }
            ]
        },
        SourceType.DASHBOARD,
    )
    assert _targets(refs) == [("entity", "sensor.hall_temp", "value")]


def test_non_string_values_and_empty_configs() -> None:
    assert _scan(None) == []
    assert _scan({"delay": 5, "enabled": False, "data": {"brightness": 255}}) == []
    assert _scan([]) == []


def test_deep_nesting_does_not_recurse() -> None:
    node: dict = {"entity_id": "light.kitchen"}
    for _ in range(5000):
        node = {"sequence": [node]}
    assert len(_scan(node)) == 1


def test_index_usage_counts_distinct_sources() -> None:
    sources = [
        ConfigSource(
            SourceType.AUTOMATION, "a1", "A1", {"e": "light.kitchen", "f": "light.kitchen"}, True
        ),
        ConfigSource(SourceType.DASHBOARD, "d1", "D1", {"entity": "light.kitchen"}, True),
    ]
    index = ReferenceIndex.build(sources, KNOWN)
    assert index.usage_count(TargetType.ENTITY, "light.kitchen") == 2
    assert len(index.references_to(entity_ids=["light.kitchen"])) == 3
