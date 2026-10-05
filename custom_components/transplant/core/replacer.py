"""Pure, side-effect-free replacement of identifiers in config trees.

``plan_item`` never mutates its input. It returns an :class:`ItemPlan`
holding a fully rewritten copy of the config plus a precise list of every
change, which the UI shows as the preview. Writing happens elsewhere.
"""

from __future__ import annotations

import re
from typing import Any

from .models import (
    Change,
    ConfigSource,
    ItemPlan,
    MatchKind,
    Replacements,
    ReviewNote,
    TargetType,
)
from .scanner import ENTITY_ID_RE, is_template, join_path

# Keys that mark the "kind" of a device automation block.
_DEVICE_BLOCK_KINDS = ("platform", "trigger", "condition")


def _is_device_automation_block(node: dict[str, Any]) -> bool:
    """Return True for device triggers, conditions and actions.

    Device triggers/conditions use ``platform``/``trigger``/``condition:
    device``; device actions are dicts with ``device_id`` + ``domain`` +
    ``type`` and no ``action``/``service`` key.
    """
    if not isinstance(node.get("device_id"), str) or "domain" not in node:
        return False
    if any(node.get(key) == "device" for key in _DEVICE_BLOCK_KINDS):
        return True
    return "type" in node and "action" not in node and "service" not in node


class _Rewriter:
    """Walks a config tree and rebuilds it with replacements applied."""

    def __init__(self, replacements: Replacements) -> None:
        self.r = replacements
        self.changes: list[Change] = []
        self.review: list[ReviewNote] = []
        entity_ids = sorted(replacements.entities, key=len, reverse=True)
        self._entity_template_re = (
            re.compile(
                r"(?<![\w.])(?P<prefix>states\.)?(?P<id>"
                + "|".join(re.escape(e) for e in entity_ids)
                + r")(?![\w])"
            )
            if entity_ids
            else None
        )
        hex_ids = {**replacements.devices, **replacements.entity_registry_ids}
        self._hex_ids = hex_ids
        self._hex_re = (
            re.compile(
                r"(?<![0-9a-f])(?P<id>" + "|".join(re.escape(h) for h in hex_ids) + r")(?![0-9a-f])"
            )
            if hex_ids
            else None
        )

    # -- public -----------------------------------------------------------

    def rewrite(self, obj: Any, path: str = "") -> Any:
        """Return a rewritten deep copy of ``obj``."""
        if isinstance(obj, str):
            return self._rewrite_string(obj, path)
        if isinstance(obj, list):
            return [self.rewrite(value, join_path(path, i)) for i, value in enumerate(obj)]
        if isinstance(obj, dict):
            return self._rewrite_dict(obj, path)
        return obj

    # -- internals --------------------------------------------------------

    def _rewrite_dict(self, node: dict[str, Any], path: str) -> dict[str, Any]:
        if _is_device_automation_block(node) and self._needs_review(node):
            self.review.append(
                ReviewNote(
                    path=path or "(root)",
                    reason=(
                        f"Device automation of integration '{node['domain']}'. "
                        f"The new device uses '{self.r.new_integration}', so this "
                        "trigger/action type may not exist on it. Left unchanged."
                    ),
                )
            )
            return dict(node)

        result: dict[Any, Any] = {}
        for key, value in node.items():
            child_path = join_path(path, str(key))
            new_key = key
            if isinstance(key, str) and (hit := self.r.lookup(key)) is not None:
                target_type, new_key = hit
                if new_key in node and new_key != key:
                    # Would silently merge two scene entries; never do that.
                    self.review.append(
                        ReviewNote(
                            path=child_path,
                            reason=f"'{new_key}' already exists here; not merged.",
                        )
                    )
                    new_key = key
                else:
                    self.changes.append(
                        Change(child_path, key, new_key, MatchKind.KEY, target_type)
                    )
            result[new_key] = self.rewrite(value, child_path)
        return result

    def _needs_review(self, node: dict[str, Any]) -> bool:
        """Integration-specific device blocks are unsafe across integrations."""
        old, new = self.r.old_integration, self.r.new_integration
        return (
            old is not None
            and new is not None
            and old != new
            and node.get("domain") == old
            and node.get("device_id") in self.r.devices
        )

    def _rewrite_string(self, value: str, path: str) -> str:
        if (hit := self.r.lookup(value)) is not None:
            target_type, new = hit
            self.changes.append(Change(path, value, new, MatchKind.VALUE, target_type))
            return new

        if is_template(value):
            return self._rewrite_template(value, path)

        if "," in value and self.r.entities:
            parts = value.split(",")
            new_parts: list[str] = []
            changed = False
            for part in parts:
                token = part.strip()
                if ENTITY_ID_RE.match(token) and token in self.r.entities:
                    new_token = self.r.entities[token]
                    self.changes.append(
                        Change(path, token, new_token, MatchKind.VALUE, TargetType.ENTITY)
                    )
                    new_parts.append(part.replace(token, new_token))
                    changed = True
                else:
                    new_parts.append(part)
            if changed:
                return ",".join(new_parts)
        return value

    def _rewrite_template(self, value: str, path: str) -> str:
        new_value = value
        if self._entity_template_re is not None:

            def _entity(match: re.Match[str]) -> str:
                old = match.group("id")
                new = self.r.entities[old]
                self.changes.append(Change(path, old, new, MatchKind.TEMPLATE, TargetType.ENTITY))
                return (match.group("prefix") or "") + new

            new_value = self._entity_template_re.sub(_entity, new_value)

        if self._hex_re is not None:

            def _hex(match: re.Match[str]) -> str:
                old = match.group("id")
                target_type = (
                    TargetType.DEVICE if old in self.r.devices else TargetType.ENTITY_REGISTRY_ID
                )
                new = self._hex_ids[old]
                self.changes.append(Change(path, old, new, MatchKind.TEMPLATE, target_type))
                return new

            new_value = self._hex_re.sub(_hex, new_value)
        return new_value


def plan_item(source: ConfigSource, replacements: Replacements) -> ItemPlan:
    """Compute all changes for one configuration object."""
    rewriter = _Rewriter(replacements)
    updated = rewriter.rewrite(source.config)
    return ItemPlan(
        source=source,
        updated_config=updated,
        changes=rewriter.changes,
        review=rewriter.review,
    )
