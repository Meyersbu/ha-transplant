"""Data models for Transplant's analysis engine.

Everything in ``transplant.core`` is pure Python with no Home Assistant
imports, so it can be unit-tested quickly and reused by future front ends.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    """Kinds of configuration objects Transplant scans."""

    AUTOMATION = "automation"
    SCRIPT = "script"
    SCENE = "scene"
    DASHBOARD = "dashboard"


class TargetType(StrEnum):
    """Kinds of identifiers a reference can point to."""

    ENTITY = "entity"
    DEVICE = "device"
    # Device automations reference entities by their registry UUID, not by
    # entity_id. We track those separately so they can be remapped too.
    ENTITY_REGISTRY_ID = "entity_registry_id"


class MatchKind(StrEnum):
    """How a reference was found."""

    VALUE = "value"  # an exact string value, e.g. entity_id: light.kitchen
    KEY = "key"  # a mapping key, e.g. scene entities: {light.kitchen: on}
    TEMPLATE = "template"  # a token inside a Jinja template string


@dataclass(slots=True, frozen=True)
class ConfigSource:
    """One scannable configuration object (an automation, a dashboard, ...)."""

    source_type: SourceType
    source_id: str  # stable key used to write it back (automation id, url_path)
    name: str
    config: Any
    editable: bool
    entity_id: str | None = None  # e.g. automation.arrive_home, if known
    read_only_reason: str | None = None


@dataclass(slots=True, frozen=True)
class Reference:
    """A single place where a configuration object refers to a target."""

    source_type: SourceType
    source_id: str
    target_type: TargetType
    target_id: str
    path: str
    kind: MatchKind

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(slots=True, frozen=True)
class Change:
    """One planned replacement inside a configuration object."""

    path: str
    old: str
    new: str
    kind: MatchKind
    target_type: TargetType

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(slots=True)
class ReviewNote:
    """A spot Transplant deliberately does not change automatically."""

    path: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(slots=True)
class ItemPlan:
    """All planned changes for one configuration object."""

    source: ConfigSource
    updated_config: Any
    changes: list[Change] = field(default_factory=list)
    review: list[ReviewNote] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary (without full configs)."""
        return {
            "source_type": self.source.source_type,
            "source_id": self.source.source_id,
            "name": self.source.name,
            "entity_id": self.source.entity_id,
            "editable": self.source.editable,
            "read_only_reason": self.source.read_only_reason,
            "changes": [change.as_dict() for change in self.changes],
            "review": [note.as_dict() for note in self.review],
        }


@dataclass(slots=True, frozen=True)
class Replacements:
    """Old-to-new identifier mappings for one replacement run."""

    entities: dict[str, str] = field(default_factory=dict)
    devices: dict[str, str] = field(default_factory=dict)
    entity_registry_ids: dict[str, str] = field(default_factory=dict)
    # Integration domain of the old/new device. When they differ,
    # integration-specific device triggers are flagged for review.
    old_integration: str | None = None
    new_integration: str | None = None

    def is_empty(self) -> bool:
        """Return True if nothing would be replaced."""
        return not (self.entities or self.devices or self.entity_registry_ids)

    def lookup(self, value: str) -> tuple[TargetType, str] | None:
        """Return the target type and replacement for an exact value."""
        if (new := self.entities.get(value)) is not None:
            return TargetType.ENTITY, new
        if (new := self.devices.get(value)) is not None:
            return TargetType.DEVICE, new
        if (new := self.entity_registry_ids.get(value)) is not None:
            return TargetType.ENTITY_REGISTRY_ID, new
        return None


@dataclass(slots=True, frozen=True)
class EntityInfo:
    """The subset of entity registry data the matcher needs."""

    entity_id: str
    registry_id: str
    domain: str
    device_class: str | None = None
    unit: str | None = None
    translation_key: str | None = None
    original_name: str | None = None
    entity_category: str | None = None
    platform: str | None = None


@dataclass(slots=True, frozen=True)
class EntityMatch:
    """A suggested old→new entity pairing."""

    old_entity_id: str
    new_entity_id: str | None
    score: int
    confidence: str  # "high" | "medium" | "low" | "none"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)
