"""Pure-Python analysis engine for Transplant (no Home Assistant imports)."""

from .models import (
    Change,
    ConfigSource,
    EntityInfo,
    EntityMatch,
    ItemPlan,
    MatchKind,
    Reference,
    Replacements,
    ReviewNote,
    SourceType,
    TargetType,
)
from .planner import Plan, build_plan, fingerprint, suggest_entity_mapping
from .replacer import plan_item
from .scanner import KnownIds, ReferenceIndex, scan_source

__all__ = [
    "Change",
    "ConfigSource",
    "EntityInfo",
    "EntityMatch",
    "ItemPlan",
    "KnownIds",
    "MatchKind",
    "Plan",
    "Reference",
    "ReferenceIndex",
    "Replacements",
    "ReviewNote",
    "SourceType",
    "TargetType",
    "build_plan",
    "fingerprint",
    "plan_item",
    "scan_source",
    "suggest_entity_mapping",
]
