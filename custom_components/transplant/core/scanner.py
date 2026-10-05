"""Reference scanner.

The scanner walks any configuration tree (automation, script, scene or
dashboard) exactly once and reports every place that refers to a known
entity, device or entity registry entry.

Design goals:

* One generic walker instead of per-schema parsers. Home Assistant configs
  evolve constantly (``trigger`` → ``triggers``, ``service`` → ``action``),
  and custom cards use arbitrary keys. Matching *values* against a set of
  known IDs is robust to all of that.
* Near-zero false positives: a string only counts if it exactly equals an
  ID that really exists (or that the user explicitly asked to replace).
  Device and registry IDs are 32-char hex strings, so collisions are
  practically impossible.
* Linear time: lookups are hash-set based, so a scan is O(size of config).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
import re
from typing import Any

from .models import ConfigSource, MatchKind, Reference, SourceType, TargetType

ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
HEX_ID_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")
# Matches entity_id tokens inside templates, including the states.x.y form.
# The look-behind prevents matching the tail of "states.light.kitchen" twice
# and the look-ahead prevents prefix matches (light.kitchen vs light.kitchen_2).
TEMPLATE_ENTITY_RE = re.compile(
    r"(?<![\w.])(?P<prefix>states\.)?(?P<id>[a-z0-9_]+\.[a-z0-9_]+)(?![\w])"
)
TEMPLATE_MARKERS = ("{{", "{%", "{#")

Matcher = Callable[[str], TargetType | None]


def is_template(value: str) -> bool:
    """Return True if a string looks like a Jinja template."""
    return any(marker in value for marker in TEMPLATE_MARKERS)


def join_path(path: str, key: str | int) -> str:
    """Build a readable path like ``actions[1].target.entity_id``."""
    if isinstance(key, int):
        return f"{path}[{key}]"
    if not key.isidentifier():
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else key


def iter_strings(obj: Any, path: str = "") -> Iterator[tuple[str, str, bool]]:
    """Yield ``(path, string, is_key)`` for every string in a config tree.

    Iterative (explicit stack) so deeply nested dashboards cannot hit the
    recursion limit.
    """
    stack: list[tuple[str, Any]] = [(path, obj)]
    while stack:
        cur_path, cur = stack.pop()
        if isinstance(cur, str):
            yield cur_path, cur, False
        elif isinstance(cur, dict):
            for key, value in cur.items():
                child_path = join_path(cur_path, str(key))
                if isinstance(key, str):
                    yield child_path, key, True
                stack.append((child_path, value))
        elif isinstance(cur, (list, tuple)):
            for index, value in enumerate(cur):
                stack.append((join_path(cur_path, index), value))


def find_in_string(
    value: str, matcher: Matcher, *, is_key: bool = False
) -> list[tuple[TargetType, str, MatchKind]]:
    """Return all known targets referenced by a single string."""
    if is_key:
        target = matcher(value)
        return [(target, value, MatchKind.KEY)] if target else []

    target = matcher(value)
    if target is not None:
        return [(target, value, MatchKind.VALUE)]

    if is_template(value):
        found: list[tuple[TargetType, str, MatchKind]] = []
        seen: set[str] = set()
        for match in TEMPLATE_ENTITY_RE.finditer(value):
            token = match.group("id")
            if token not in seen and (target := matcher(token)) is not None:
                seen.add(token)
                found.append((target, token, MatchKind.TEMPLATE))
        for match in HEX_ID_RE.finditer(value):
            token = match.group(0)
            if token not in seen and (target := matcher(token)) is not None:
                seen.add(token)
                found.append((target, token, MatchKind.TEMPLATE))
        return found

    # Legacy comma-separated form: "entity_id: light.a, light.b"
    if "," in value:
        found = []
        for part in value.split(","):
            token = part.strip()
            if ENTITY_ID_RE.match(token) and (target := matcher(token)):
                found.append((target, token, MatchKind.VALUE))
        return found

    return []


def scan_source(source: ConfigSource, matcher: Matcher) -> list[Reference]:
    """Scan one configuration object and return all references."""
    references: list[Reference] = []
    for path, value, is_key in iter_strings(source.config):
        for target_type, target_id, kind in find_in_string(value, matcher, is_key=is_key):
            references.append(
                Reference(
                    source_type=source.source_type,
                    source_id=source.source_id,
                    target_type=target_type,
                    target_id=target_id,
                    path=path,
                    kind=kind,
                )
            )
    return references


@dataclass(slots=True)
class KnownIds:
    """Sets of identifiers that exist in this Home Assistant instance."""

    entities: set[str] = field(default_factory=set)
    devices: set[str] = field(default_factory=set)
    # registry UUID → entity_id
    registry_ids: dict[str, str] = field(default_factory=dict)
    extra_entities: set[str] = field(default_factory=set)
    extra_devices: set[str] = field(default_factory=set)

    def matcher(self) -> Matcher:
        """Return a fast lookup function for the scanner."""
        entities = self.entities | self.extra_entities
        devices = self.devices | self.extra_devices
        registry_ids = self.registry_ids

        def _match(value: str) -> TargetType | None:
            # Cheap length/shape checks first: most strings are neither.
            if len(value) == 32:
                if value in devices:
                    return TargetType.DEVICE
                if value in registry_ids:
                    return TargetType.ENTITY_REGISTRY_ID
            if "." in value and value in entities:
                return TargetType.ENTITY
            return None

        return _match


@dataclass(slots=True)
class ReferenceIndex:
    """Reverse index: target → every place it is used."""

    by_target: dict[tuple[TargetType, str], list[Reference]] = field(
        default_factory=lambda: defaultdict(list)
    )
    sources: dict[tuple[SourceType, str], ConfigSource] = field(default_factory=dict)

    @classmethod
    def build(cls, sources: Iterable[ConfigSource], known: KnownIds) -> ReferenceIndex:
        """Scan all sources once and index the results."""
        index = cls()
        matcher = known.matcher()
        for source in sources:
            index.sources[(source.source_type, source.source_id)] = source
            for reference in scan_source(source, matcher):
                index.by_target[(reference.target_type, reference.target_id)].append(reference)
        return index

    def references_to(
        self,
        *,
        entity_ids: Iterable[str] = (),
        device_ids: Iterable[str] = (),
        registry_ids: Iterable[str] = (),
    ) -> list[Reference]:
        """Return all references to any of the given targets."""
        result: list[Reference] = []
        for target_type, ids in (
            (TargetType.ENTITY, entity_ids),
            (TargetType.DEVICE, device_ids),
            (TargetType.ENTITY_REGISTRY_ID, registry_ids),
        ):
            for target_id in ids:
                result.extend(self.by_target.get((target_type, target_id), ()))
        return result

    def usage_count(self, target_type: TargetType, target_id: str) -> int:
        """Return how many distinct sources use a target."""
        refs = self.by_target.get((target_type, target_id), ())
        return len({(ref.source_type, ref.source_id) for ref in refs})


def group_by_source(
    references: Iterable[Reference],
) -> dict[tuple[SourceType, str], list[Reference]]:
    """Group references by the configuration object they live in."""
    grouped: dict[tuple[SourceType, str], list[Reference]] = defaultdict(list)
    for reference in references:
        grouped[(reference.source_type, reference.source_id)].append(reference)
    return dict(grouped)
