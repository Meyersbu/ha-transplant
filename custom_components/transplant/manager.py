"""Transplant manager: ties registries, scanner, plans, snapshots together."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import time
from typing import Any
import uuid

from homeassistant.const import (
    EVENT_CALL_SERVICE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    INDEX_MAX_AGE_SECONDS,
    MAX_PLANS,
    MAX_SNAPSHOTS,
    PLAN_TTL_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .core import (
    EntityInfo,
    KnownIds,
    Plan,
    ReferenceIndex,
    Replacements,
    SourceType,
    build_plan,
    fingerprint,
    scan_source,
    suggest_entity_mapping,
)
from .sources import (
    CollectedSources,
    TransplantWriteError,
    async_collect_sources,
    async_read_current,
    async_validate,
    async_write_items,
)

_LOGGER = logging.getLogger(__name__)

_INVALIDATING_EVENTS = (
    er.EVENT_ENTITY_REGISTRY_UPDATED,
    dr.EVENT_DEVICE_REGISTRY_UPDATED,
    "lovelace_updated",
    "automation_reloaded",
)


class PlanExpiredError(TransplantWriteError):
    """The preview is too old or unknown."""


class PlanStaleError(TransplantWriteError):
    """Configuration changed between preview and apply."""


def iter_devices(registry: dr.DeviceRegistry) -> list[dr.DeviceEntry]:
    """Iterate devices across HA versions.

    Up to 2026.8 ``registry.devices`` is a mapping (iteration yields ids);
    newer cores iterate entries directly and deprecate ``.values()``.
    """
    devices = registry.devices
    items = list(iter(devices))
    if items and isinstance(items[0], str):
        return [devices[key] for key in items]  # type: ignore[index]
    return items  # type: ignore[return-value]


def device_config_entry_id(device: dr.DeviceEntry) -> str | None:
    """Primary config entry of a device across HA versions."""
    for attr in ("config_entry_id", "primary_config_entry"):
        if value := getattr(device, attr, None):
            return str(value)
    entries = getattr(device, "config_entries", None)
    return next(iter(entries), None) if entries else None


@dataclass(slots=True)
class StoredPlan:
    """A preview waiting for confirmation."""

    plan: Plan
    title: str
    created: float


class TransplantManager:
    """Long-lived helper attached to the config entry."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._snapshots: list[dict[str, Any]] = []
        self._plans: dict[str, StoredPlan] = {}
        self._cache: tuple[float, CollectedSources, ReferenceIndex, KnownIds] | None = None
        self._unsubs: list[Callable[[], None]] = []

    # -- lifecycle --------------------------------------------------------

    async def async_setup(self) -> None:
        """Load snapshots and subscribe to invalidation events."""
        data = await self._store.async_load() or {}
        self._snapshots = list(data.get("snapshots", []))
        for event_type in _INVALIDATING_EVENTS:
            self._unsubs.append(self.hass.bus.async_listen(event_type, self._invalidate))
        self._unsubs.append(self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._on_service_call))

    @callback
    def async_unload(self) -> None:
        """Drop listeners and caches."""
        while self._unsubs:
            self._unsubs.pop()()
        self._cache = None
        self._plans.clear()

    @callback
    def _invalidate(self, _event: Event[Any] | None = None) -> None:
        self._cache = None

    @callback
    def _on_service_call(self, event: Event[Any]) -> None:
        # script.reload / scene.reload have no dedicated "reloaded" event.
        if event.data.get("service") == "reload" and event.data.get("domain") in (
            "script",
            "scene",
            "automation",
        ):
            self._cache = None

    # -- registry views ---------------------------------------------------

    def _known_ids(self) -> KnownIds:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        known = KnownIds()
        for entry in ent_reg.entities.values():
            known.entities.add(entry.entity_id)
            known.registry_ids[entry.id] = entry.entity_id
        # Entities without a registry entry (e.g. YAML template sensors).
        known.entities.update(self.hass.states.async_entity_ids())
        known.devices.update(device.id for device in iter_devices(dev_reg))
        return known

    async def async_index(
        self, *, force: bool = False
    ) -> tuple[CollectedSources, ReferenceIndex, KnownIds]:
        """Return a cached scan of the whole instance."""
        now = time.monotonic()
        if not force and self._cache and now - self._cache[0] < INDEX_MAX_AGE_SECONDS:
            return self._cache[1], self._cache[2], self._cache[3]
        collected = await async_collect_sources(self.hass)
        known = self._known_ids()
        index = ReferenceIndex.build(collected.sources, known)
        self._cache = (now, collected, index, known)
        return collected, index, known

    def _entity_info(self, entry: er.RegistryEntry) -> EntityInfo:
        category = entry.entity_category
        return EntityInfo(
            entity_id=entry.entity_id,
            registry_id=entry.id,
            domain=entry.domain,
            device_class=entry.device_class or entry.original_device_class,
            unit=entry.unit_of_measurement,
            translation_key=entry.translation_key,
            original_name=entry.original_name,
            entity_category=str(category.value) if category else None,
            platform=entry.platform,
        )

    def _device_entities(self, device_id: str) -> list[er.RegistryEntry]:
        return er.async_entries_for_device(
            er.async_get(self.hass), device_id, include_disabled_entities=True
        )

    def _integration(self, device: dr.DeviceEntry) -> str | None:
        entry_id = device_config_entry_id(device)
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        return entry.domain if entry else None

    def _is_unavailable(self, entries: list[er.RegistryEntry]) -> bool:
        states = [
            state
            for e in entries
            if not e.disabled_by and (state := self.hass.states.get(e.entity_id)) is not None
        ]
        if not states:
            return True
        return all(s.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) for s in states)

    def device_usage_refs(self, index: ReferenceIndex, device_id: str) -> list[Any]:
        """All references to a device and its entities."""
        entries = self._device_entities(device_id)
        return index.references_to(
            entity_ids=[e.entity_id for e in entries],
            device_ids=[device_id],
            registry_ids=[e.id for e in entries],
        )

    # -- read API ---------------------------------------------------------

    async def async_overview(self) -> dict[str, Any]:
        """Devices with usage counts + scan stats + snapshot history."""
        collected, index, _known = await self.async_index()
        dev_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        devices: list[dict[str, Any]] = []
        for device in iter_devices(dev_reg):
            if device.entry_type is dr.DeviceEntryType.SERVICE:
                continue
            entries = self._device_entities(device.id)
            refs = self.device_usage_refs(index, device.id)
            area = area_reg.async_get_area(device.area_id) if device.area_id else None
            created = getattr(device, "created_at", None)
            devices.append(
                {
                    "id": device.id,
                    "name": device.name_by_user or device.name or device.id,
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "area": area.name if area else None,
                    "integration": self._integration(device),
                    "entity_count": len(entries),
                    "unavailable": self._is_unavailable(entries),
                    "used_in": len({(r.source_type, r.source_id) for r in refs}),
                    "created_at": created.isoformat() if created else None,
                }
            )
        stats: dict[str, int] = {}
        read_only = 0
        for source in collected.sources:
            stats[str(source.source_type)] = stats.get(str(source.source_type), 0) + 1
            read_only += 0 if source.editable else 1
        return {
            "devices": devices,
            "stats": {**stats, "read_only": read_only},
            "warnings": collected.warnings,
            "snapshots": [self._snapshot_summary(s) for s in reversed(self._snapshots)],
        }

    async def async_device_usage(self, device_id: str) -> dict[str, Any]:
        """Where a device and its entities are used, grouped by object."""
        collected, index, _known = await self.async_index()
        refs = self.device_usage_refs(index, device_id)
        grouped: dict[tuple[SourceType, str], list[Any]] = {}
        for ref in refs:
            grouped.setdefault((ref.source_type, ref.source_id), []).append(ref)
        items = []
        for (source_type, source_id), item_refs in sorted(
            grouped.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
        ):
            source = collected.get(source_type, source_id)
            items.append(
                {
                    "source_type": source_type,
                    "source_id": source_id,
                    "name": source.name if source else source_id,
                    "entity_id": source.entity_id if source else None,
                    "editable": source.editable if source else False,
                    "references": [r.as_dict() for r in item_refs],
                }
            )
        return {"device_id": device_id, "items": items}

    def suggest(self, old_device_id: str, new_device_id: str) -> dict[str, Any]:
        """Suggest which new entity replaces which old entity."""
        old = [self._entity_info(e) for e in self._device_entities(old_device_id)]
        new = [self._entity_info(e) for e in self._device_entities(new_device_id)]
        matches = suggest_entity_mapping(old, new)

        def _describe(info: EntityInfo) -> dict[str, Any]:
            state = self.hass.states.get(info.entity_id)
            return {
                "entity_id": info.entity_id,
                "name": (state.name if state else None) or info.original_name or info.entity_id,
                "domain": info.domain,
                "device_class": info.device_class,
                "unit": info.unit,
                "state": state.state if state else None,
            }

        return {
            "matches": [m.as_dict() for m in matches],
            "old_entities": [_describe(i) for i in old],
            "new_entities": [_describe(i) for i in new],
        }

    # -- plan / apply / undo ----------------------------------------------

    def _replacements_for(
        self,
        old_device_id: str | None,
        new_device_id: str | None,
        entity_map: dict[str, str | None],
    ) -> Replacements:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        entities = {old: new for old, new in entity_map.items() if new and new != old}
        registry_ids: dict[str, str] = {}
        for old, new in entities.items():
            old_entry, new_entry = ent_reg.async_get(old), ent_reg.async_get(new)
            if old_entry and new_entry:
                registry_ids[old_entry.id] = new_entry.id
        devices: dict[str, str] = {}
        old_integration = new_integration = None
        if old_device_id and new_device_id and old_device_id != new_device_id:
            devices[old_device_id] = new_device_id
            if (old_dev := dev_reg.async_get(old_device_id)) is not None:
                old_integration = self._integration(old_dev)
            if (new_dev := dev_reg.async_get(new_device_id)) is not None:
                new_integration = self._integration(new_dev)
        return Replacements(
            entities=entities,
            devices=devices,
            entity_registry_ids=registry_ids,
            old_integration=old_integration,
            new_integration=new_integration,
        )

    async def async_preview(
        self,
        old_device_id: str | None,
        new_device_id: str | None,
        entity_map: dict[str, str | None],
    ) -> dict[str, Any]:
        """Build a plan and keep it for confirmation."""
        replacements = self._replacements_for(old_device_id, new_device_id, entity_map)
        if replacements.is_empty():
            raise TransplantWriteError("Nothing to replace: choose at least one new entity.")
        collected, index, known = await self.async_index(force=True)
        # Old IDs may no longer exist (dead device removed). Scan for them anyway.
        if set(replacements.entities) - known.entities or set(replacements.devices) - known.devices:
            known.extra_entities |= set(replacements.entities)
            known.extra_devices |= set(replacements.devices)
            index = ReferenceIndex.build(collected.sources, known)
        plan = build_plan(collected.sources, index, replacements)

        title = self._plan_title(old_device_id, new_device_id, replacements)
        self._prune_plans()
        plan_id = uuid.uuid4().hex
        self._plans[plan_id] = StoredPlan(plan, title, time.monotonic())
        return {"plan_id": plan_id, "title": title, **plan.as_dict()}

    def _plan_title(
        self, old_device_id: str | None, new_device_id: str | None, r: Replacements
    ) -> str:
        dev_reg = dr.async_get(self.hass)
        if old_device_id and new_device_id:
            old = dev_reg.async_get(old_device_id)
            new = dev_reg.async_get(new_device_id)
            old_name = (old.name_by_user or old.name) if old else old_device_id
            new_name = (new.name_by_user or new.name) if new else new_device_id
            return f"{old_name} → {new_name}"
        first = next(iter(r.entities.items()))
        return f"{first[0]} → {first[1]}"

    def _prune_plans(self) -> None:
        now = time.monotonic()
        for plan_id in [p for p, s in self._plans.items() if now - s.created > PLAN_TTL_SECONDS]:
            del self._plans[plan_id]
        while len(self._plans) >= MAX_PLANS:
            del self._plans[next(iter(self._plans))]

    async def async_apply(self, plan_id: str) -> dict[str, Any]:
        """Validate → snapshot → write → reload → verify. Rolls back on failure."""
        self._prune_plans()
        stored = self._plans.pop(plan_id, None)
        if stored is None:
            raise PlanExpiredError("This preview expired. Create a new preview.")
        plan = stored.plan
        items = plan.editable_items
        if not items:
            raise TransplantWriteError("Nothing editable to change.")

        by_type: dict[SourceType, dict[str, Any]] = {}
        for item in items:
            by_type.setdefault(item.source.source_type, {})[item.source.source_id] = item

        # 1. Stale check against what is on disk right now.
        originals: dict[SourceType, dict[str, Any]] = {}
        for source_type, type_items in by_type.items():
            current = await async_read_current(self.hass, source_type, type_items)
            for source_id in type_items:
                key = (source_type, source_id)
                if (
                    source_id not in current
                    or fingerprint(current[source_id]) != plan.fingerprints[key]
                ):
                    raise PlanStaleError(
                        f"{source_type} '{type_items[source_id].source.name}' changed "
                        "since the preview. Create a new preview."
                    )
            originals[source_type] = current

        # 2. Validate every updated item before touching anything.
        for source_type, type_items in by_type.items():
            for source_id, item in type_items.items():
                await async_validate(self.hass, source_type, source_id, item.updated_config)

        # 3. Snapshot.
        snapshot = {
            "id": uuid.uuid4().hex,
            "created": dt_util.utcnow().isoformat(),
            "title": stored.title,
            "undone": False,
            "replacements": sum(len(i.changes) for i in items),
            "items": [
                {
                    "source_type": str(i.source.source_type),
                    "source_id": i.source.source_id,
                    "name": i.source.name,
                    "before": originals[i.source.source_type][i.source.source_id],
                    "after": i.updated_config,
                }
                for i in items
            ],
        }
        await self._save_snapshot(snapshot)

        # 4. Write per type; roll back already-written types on failure.
        written: list[SourceType] = []
        try:
            for source_type, type_items in by_type.items():
                await async_write_items(
                    self.hass,
                    source_type,
                    {sid: item.updated_config for sid, item in type_items.items()},
                )
                written.append(source_type)
        except Exception as err:
            _LOGGER.error("Transplant apply failed, rolling back: %s", err)
            for source_type in written:
                await async_write_items(self.hass, source_type, originals[source_type])
            snapshot["undone"] = True
            await self._persist()
            raise TransplantWriteError(f"Apply failed and was rolled back: {err}") from err

        self._invalidate()
        verification = await self._verify(plan)
        return {
            "snapshot_id": snapshot["id"],
            "objects": len(items),
            "replacements": snapshot["replacements"],
            "verification": verification,
        }

    async def _verify(self, plan: Plan) -> dict[str, Any]:
        """Re-scan and confirm no editable object still uses an old ID."""
        collected, _index, _known = await self.async_index(force=True)
        old_ids = (
            set(plan.replacements.entities)
            | set(plan.replacements.devices)
            | set(plan.replacements.entity_registry_ids)
        )
        reviewed_paths = {
            (i.source.source_type, i.source.source_id): {n.path for n in i.review}
            for i in plan.items
        }
        matcher_known = KnownIds(extra_entities=set(plan.replacements.entities))
        matcher_known.extra_devices = set(plan.replacements.devices)
        matcher_known.registry_ids = dict.fromkeys(plan.replacements.entity_registry_ids, "")
        matcher = matcher_known.matcher()
        leftovers: list[dict[str, Any]] = []
        for item in plan.editable_items:
            source = collected.get(item.source.source_type, item.source.source_id)
            if source is None:
                leftovers.append({"source_id": item.source.source_id, "path": "(missing)"})
                continue
            skip = reviewed_paths.get((source.source_type, source.source_id), set())
            for ref in scan_source(source, matcher):
                if ref.target_id in old_ids and not any(ref.path.startswith(p) for p in skip):
                    leftovers.append({"source_id": source.source_id, "path": ref.path})
        unavailable = []
        for item in plan.editable_items:
            entity_id = item.source.entity_id
            if (
                entity_id
                and (state := self.hass.states.get(entity_id))
                and state.state == STATE_UNAVAILABLE
            ):
                unavailable.append(entity_id)
        return {
            "ok": not leftovers and not unavailable,
            "leftovers": leftovers,
            "unavailable": unavailable,
        }

    async def async_undo(self, snapshot_id: str) -> dict[str, Any]:
        """Restore objects that have not been edited since the snapshot."""
        snapshot = next((s for s in self._snapshots if s["id"] == snapshot_id), None)
        if snapshot is None:
            raise TransplantWriteError("Snapshot not found.")
        if snapshot.get("undone"):
            raise TransplantWriteError("This change was already undone.")
        by_type: dict[SourceType, list[dict[str, Any]]] = {}
        for item in snapshot["items"]:
            by_type.setdefault(SourceType(item["source_type"]), []).append(item)

        restored, conflicts = 0, []
        for source_type, items in by_type.items():
            current = await async_read_current(
                self.hass, source_type, [i["source_id"] for i in items]
            )
            updates = {}
            for item in items:
                now = current.get(item["source_id"])
                if now is not None and fingerprint(now) == fingerprint(item["after"]):
                    updates[item["source_id"]] = item["before"]
                else:
                    conflicts.append(item["name"])
            await async_write_items(self.hass, source_type, updates)
            restored += len(updates)
        snapshot["undone"] = True
        await self._persist()
        self._invalidate()
        return {"restored": restored, "conflicts": conflicts}

    # -- snapshots --------------------------------------------------------

    def _snapshot_summary(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": snapshot["id"],
            "created": snapshot["created"],
            "title": snapshot["title"],
            "undone": snapshot.get("undone", False),
            "objects": len(snapshot["items"]),
            "replacements": snapshot.get("replacements", 0),
        }

    async def _save_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._snapshots.append(snapshot)
        del self._snapshots[:-MAX_SNAPSHOTS]
        await self._persist()

    async def _persist(self) -> None:
        await self._store.async_save({"snapshots": self._snapshots})

    async def async_remove_storage(self) -> None:
        """Delete stored snapshots (called when the integration is removed)."""
        await self._store.async_remove()
