"""Entity matching for device swaps and assembly of a replacement plan."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any

from .models import (
    ConfigSource,
    EntityInfo,
    EntityMatch,
    ItemPlan,
    Replacements,
    SourceType,
)
from .replacer import plan_item
from .scanner import ReferenceIndex, group_by_source

_NON_WORD = re.compile(r"[^a-z0-9]+")


def _norm(value: str | None) -> str:
    return _NON_WORD.sub(" ", (value or "").lower()).strip()


def _object_suffix(entity_id: str) -> str:
    """Last word of the object id, e.g. sensor.hall_motion_battery → battery."""
    return entity_id.split(".", 1)[1].rsplit("_", 1)[-1]


def score_pair(old: EntityInfo, new: EntityInfo) -> int:
    """Score how likely ``new`` is the replacement for ``old`` (0 = no)."""
    if old.domain != new.domain:
        return 0
    score = 1
    if old.device_class and old.device_class == new.device_class:
        score += 3
    if old.unit and old.unit == new.unit:
        score += 2
    if old.translation_key and old.translation_key == new.translation_key:
        score += 2
    if old.original_name and _norm(old.original_name) == _norm(new.original_name):
        score += 2
    if _object_suffix(old.entity_id) == _object_suffix(new.entity_id):
        score += 1
    if old.entity_category == new.entity_category:
        score += 1
    # A different device_class within the same domain is a strong negative
    # signal (e.g. temperature vs humidity sensor).
    if old.device_class and new.device_class and old.device_class != new.device_class:
        score -= 4
    return max(score, 0)


def _confidence(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    if score >= 1:
        return "low"
    return "none"


def suggest_entity_mapping(
    old_entities: Sequence[EntityInfo], new_entities: Sequence[EntityInfo]
) -> list[EntityMatch]:
    """Greedy best-first matching of old to new entities.

    Devices have a handful of entities, so scoring all pairs (n·m) is cheap.
    Each new entity is used at most once.
    """
    candidates: list[tuple[int, int, int]] = []
    for i, old in enumerate(old_entities):
        for j, new in enumerate(new_entities):
            if (score := score_pair(old, new)) > 0:
                candidates.append((score, i, j))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))

    used_old: dict[int, tuple[int, int]] = {}
    used_new: set[int] = set()
    for score, i, j in candidates:
        if i in used_old or j in used_new:
            continue
        used_old[i] = (j, score)
        used_new.add(j)

    result: list[EntityMatch] = []
    for i, old in enumerate(old_entities):
        if i in used_old:
            j, score = used_old[i]
            result.append(
                EntityMatch(old.entity_id, new_entities[j].entity_id, score, _confidence(score))
            )
        else:
            result.append(EntityMatch(old.entity_id, None, 0, "none"))
    return result


def fingerprint(config: Any) -> str:
    """Stable hash of a config, used to detect edits between preview and apply."""
    payload = json.dumps(config, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(slots=True)
class Plan:
    """A complete, reviewable replacement plan."""

    replacements: Replacements
    items: list[ItemPlan] = field(default_factory=list)
    fingerprints: dict[tuple[SourceType, str], str] = field(default_factory=dict)

    @property
    def editable_items(self) -> list[ItemPlan]:
        """Items Transplant can write back."""
        return [i for i in self.items if i.source.editable and i.changes]

    @property
    def read_only_items(self) -> list[ItemPlan]:
        """Items that reference the old IDs but cannot be edited safely."""
        return [i for i in self.items if not i.source.editable and i.changes]

    def summary(self) -> dict[str, Any]:
        """Counts shown in the preview header."""
        per_type: dict[str, int] = {}
        for item in self.editable_items:
            key = str(item.source.source_type)
            per_type[key] = per_type.get(key, 0) + 1
        return {
            "objects": len(self.editable_items),
            "replacements": sum(len(i.changes) for i in self.editable_items),
            "by_type": per_type,
            "read_only": len(self.read_only_items),
            "needs_review": sum(len(i.review) for i in self.items),
        }

    def as_dict(self) -> dict[str, Any]:
        """JSON-serializable plan for the frontend."""
        return {
            "summary": self.summary(),
            "items": [item.as_dict() for item in self.items if item.changes or item.review],
        }


def build_plan(
    sources: Iterable[ConfigSource],
    index: ReferenceIndex,
    replacements: Replacements,
) -> Plan:
    """Plan replacements only for sources that actually reference old IDs.

    The reverse index narrows the work down first, so planning a swap in a
    large installation only rewrites the handful of affected objects.
    """
    plan = Plan(replacements=replacements)
    refs = index.references_to(
        entity_ids=replacements.entities,
        device_ids=replacements.devices,
        registry_ids=replacements.entity_registry_ids,
    )
    affected = group_by_source(refs)
    by_key = {(s.source_type, s.source_id): s for s in sources}
    for key in sorted(affected, key=lambda k: (str(k[0]), k[1])):
        source = by_key.get(key)
        if source is None:
            continue
        item = plan_item(source, replacements)
        if item.changes or item.review:
            plan.items.append(item)
            plan.fingerprints[key] = fingerprint(source.config)
    return plan
