"""Synthetic Home Assistant installations for tests and benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
import random
import uuid

from transplant_core import ConfigSource, KnownIds, SourceType

DOMAINS = ("light", "switch", "sensor", "binary_sensor", "cover", "climate")


@dataclass
class Installation:
    """A fake instance: known IDs plus scannable config sources."""

    known: KnownIds
    sources: list[ConfigSource]
    entity_ids: list[str]
    device_ids: list[str]


def make_installation(
    n_entities: int,
    n_devices: int,
    n_automations: int,
    n_dashboards: int,
    seed: int = 1,
) -> Installation:
    """Build a deterministic fake installation of the requested size."""
    rnd = random.Random(seed)
    entity_ids = [f"{DOMAINS[i % len(DOMAINS)]}.entity_{i}" for i in range(n_entities)]
    device_ids = [uuid.UUID(int=rnd.getrandbits(128)).hex for _ in range(n_devices)]
    registry_ids = {uuid.UUID(int=rnd.getrandbits(128)).hex: e for e in entity_ids}
    known = KnownIds(entities=set(entity_ids), devices=set(device_ids), registry_ids=registry_ids)

    sources: list[ConfigSource] = []
    for a in range(n_automations):
        e1, e2, e3 = rnd.sample(entity_ids, 3)
        dev = rnd.choice(device_ids)
        config = {
            "id": f"auto_{a}",
            "alias": f"Automation {a}",
            "triggers": [
                {"trigger": "state", "entity_id": [e1], "to": "on"},
                {
                    "trigger": "device",
                    "device_id": dev,
                    "domain": "zha",
                    "type": "remote_button_short_press",
                },
            ],
            "conditions": [
                {
                    "condition": "template",
                    "value_template": f"{{{{ is_state('{e2}', 'on') }}}}",
                }
            ],
            "actions": [
                {"action": "light.turn_on", "target": {"entity_id": e3}},
                {
                    "choose": [
                        {
                            "conditions": [],
                            "sequence": [
                                {"delay": 5},
                                {"action": "notify.notify", "data": {"message": "hi"}},
                            ],
                        }
                    ]
                },
            ],
        }
        sources.append(
            ConfigSource(SourceType.AUTOMATION, f"auto_{a}", f"Automation {a}", config, True)
        )
    for d in range(n_dashboards):
        cards = [{"type": "tile", "entity": e} for e in rnd.sample(entity_ids, min(40, n_entities))]
        config = {"views": [{"title": "Home", "sections": [{"type": "grid", "cards": cards}]}]}
        sources.append(
            ConfigSource(SourceType.DASHBOARD, f"dash-{d}", f"Dashboard {d}", config, True)
        )
    return Installation(known, sources, entity_ids, device_ids)
