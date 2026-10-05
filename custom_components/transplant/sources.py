"""Read and write Home Assistant configuration objects.

Transplant only writes to the places Home Assistant's own UI editors write
to, using the same mechanics:

* ``automations.yaml`` / ``scripts.yaml`` / ``scenes.yaml`` via
  ``homeassistant.util.yaml.dump`` + ``write_utf8_file_atomic`` (exactly what
  the core config editor does), followed by the matching reload service.
* Storage-mode dashboards via the Lovelace dashboard object's ``async_save``.

Everything else (YAML packages, YAML-mode dashboards) is scanned read-only
and reported, never modified.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import logging
import os
from typing import Any

from homeassistant.config import (
    AUTOMATION_CONFIG_PATH,
    SCENE_CONFIG_PATH,
    SCRIPT_CONFIG_PATH,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, load_yaml

from .const import DEFAULT_DASHBOARD_ID
from .core import ConfigSource, SourceType

_LOGGER = logging.getLogger(__name__)

READ_ONLY_YAML = "Defined in YAML outside the UI editor (e.g. packages). Edit it manually."
READ_ONLY_DASHBOARD = "YAML-mode dashboard. Edit its YAML file manually."


class TransplantWriteError(HomeAssistantError):
    """Raised when a configuration object could not be written."""


def _read_yaml(path: str) -> Any:
    if not os.path.isfile(path):
        return None
    return load_yaml(path)


def _write_yaml(path: str, data: Any) -> None:
    # Dump first so a serialization error can never truncate the file.
    contents = dump(data)
    write_utf8_file_atomic(path, contents)


def _component_entities(hass: HomeAssistant, domain: str) -> list[Any]:
    """Return entities of an EntityComponent (automation/script), defensively."""
    component = hass.data.get(domain)
    entities = getattr(component, "entities", None)
    return list(entities) if entities is not None else []


@dataclass(slots=True)
class CollectedSources:
    """All configuration objects plus raw file contents for writing."""

    sources: list[ConfigSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def get(self, source_type: SourceType, source_id: str) -> ConfigSource | None:
        """Look up one source."""
        for source in self.sources:
            if source.source_type is source_type and source.source_id == source_id:
                return source
        return None


async def async_collect_sources(hass: HomeAssistant) -> CollectedSources:
    """Load every scannable configuration object."""
    result = CollectedSources()
    for loader in (_collect_automations, _collect_scripts, _collect_scenes, _collect_dashboards):
        try:
            await loader(hass, result)
        except Exception as err:  # noqa: BLE001 - one broken source must not kill the scan
            _LOGGER.warning("Transplant could not scan %s: %s", loader.__name__, err)
            result.warnings.append(f"{loader.__name__.removeprefix('_collect_')}: {err}")
    return result


async def _collect_automations(hass: HomeAssistant, result: CollectedSources) -> None:
    ent_reg = er.async_get(hass)
    data = await hass.async_add_executor_job(_read_yaml, hass.config.path(AUTOMATION_CONFIG_PATH))
    file_ids: set[str] = set()
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or "id" not in item:
            continue
        key = str(item["id"])
        file_ids.add(key)
        result.sources.append(
            ConfigSource(
                SourceType.AUTOMATION,
                key,
                str(item.get("alias") or key),
                item,
                editable=True,
                entity_id=ent_reg.async_get_entity_id("automation", "automation", key),
            )
        )
    for entity in _component_entities(hass, "automation"):
        raw = getattr(entity, "raw_config", None)
        if not isinstance(raw, dict) or entity.unique_id in file_ids:
            continue
        result.sources.append(
            ConfigSource(
                SourceType.AUTOMATION,
                f"yaml:{entity.entity_id}",
                str(raw.get("alias") or entity.entity_id),
                raw,
                editable=False,
                entity_id=entity.entity_id,
                read_only_reason=READ_ONLY_YAML,
            )
        )


async def _collect_scripts(hass: HomeAssistant, result: CollectedSources) -> None:
    data = await hass.async_add_executor_job(_read_yaml, hass.config.path(SCRIPT_CONFIG_PATH))
    file_ids: set[str] = set()
    for key, item in data.items() if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        file_ids.add(str(key))
        result.sources.append(
            ConfigSource(
                SourceType.SCRIPT,
                str(key),
                str(item.get("alias") or key),
                item,
                editable=True,
                entity_id=f"script.{key}",
            )
        )
    for entity in _component_entities(hass, "script"):
        raw = getattr(entity, "raw_config", None)
        object_id = entity.entity_id.split(".", 1)[1]
        if not isinstance(raw, dict) or object_id in file_ids:
            continue
        result.sources.append(
            ConfigSource(
                SourceType.SCRIPT,
                f"yaml:{entity.entity_id}",
                str(raw.get("alias") or entity.entity_id),
                raw,
                editable=False,
                entity_id=entity.entity_id,
                read_only_reason=READ_ONLY_YAML,
            )
        )


async def _collect_scenes(hass: HomeAssistant, result: CollectedSources) -> None:
    ent_reg = er.async_get(hass)
    data = await hass.async_add_executor_job(_read_yaml, hass.config.path(SCENE_CONFIG_PATH))
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or "id" not in item:
            continue
        key = str(item["id"])
        result.sources.append(
            ConfigSource(
                SourceType.SCENE,
                key,
                str(item.get("name") or key),
                item,
                editable=True,
                entity_id=ent_reg.async_get_entity_id("scene", "homeassistant", key),
            )
        )


def _lovelace_dashboards(hass: HomeAssistant) -> dict[str | None, Any]:
    data = hass.data.get("lovelace")
    dashboards = getattr(data, "dashboards", None)
    if dashboards is None and isinstance(data, dict):  # very old cores
        dashboards = data.get("dashboards")
    return dict(dashboards or {})


async def _collect_dashboards(hass: HomeAssistant, result: CollectedSources) -> None:
    for url_path, dashboard in _lovelace_dashboards(hass).items():
        try:
            config = await dashboard.async_load(False)
        except HomeAssistantError:
            continue  # empty / auto-generated dashboard, nothing to scan
        if not isinstance(config, dict) or "strategy" in config:
            continue
        meta = getattr(dashboard, "config", None) or {}
        source_id = url_path or DEFAULT_DASHBOARD_ID
        editable = getattr(dashboard, "mode", None) == "storage"
        result.sources.append(
            ConfigSource(
                SourceType.DASHBOARD,
                source_id,
                str(
                    meta.get("title")
                    or config.get("title")
                    or ("Overview" if url_path is None else url_path)
                ),
                config,
                editable=editable,
                read_only_reason=None if editable else READ_ONLY_DASHBOARD,
            )
        )


async def async_read_current(
    hass: HomeAssistant, source_type: SourceType, source_ids: Iterable[str]
) -> dict[str, Any]:
    """Read the *current* config of editable objects straight from disk/storage."""
    wanted = set(source_ids)
    current: dict[str, Any] = {}
    if source_type is SourceType.DASHBOARD:
        for url_path, dashboard in _lovelace_dashboards(hass).items():
            key = url_path or DEFAULT_DASHBOARD_ID
            if key in wanted:
                try:
                    current[key] = await dashboard.async_load(True)
                except HomeAssistantError:
                    current[key] = None
        return current

    path = hass.config.path(_FILES[source_type])
    data = await hass.async_add_executor_job(_read_yaml, path)
    if source_type is SourceType.SCRIPT:
        for key, item in data.items() if isinstance(data, dict) else []:
            if str(key) in wanted:
                current[str(key)] = item
    else:
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict) and str(item.get("id")) in wanted:
                current[str(item["id"])] = item
    return current


_FILES = {
    SourceType.AUTOMATION: AUTOMATION_CONFIG_PATH,
    SourceType.SCRIPT: SCRIPT_CONFIG_PATH,
    SourceType.SCENE: SCENE_CONFIG_PATH,
}
_RELOAD = {
    SourceType.AUTOMATION: "automation",
    SourceType.SCRIPT: "script",
    SourceType.SCENE: "scene",
}


async def async_validate(
    hass: HomeAssistant, source_type: SourceType, source_id: str, config: Any
) -> None:
    """Validate an updated item with Home Assistant's own validators."""
    try:
        if source_type is SourceType.AUTOMATION:
            from homeassistant.components.automation.config import (  # noqa: PLC0415
                async_validate_config_item,
            )

            validated: Any = await async_validate_config_item(hass, source_id, config)
        elif source_type is SourceType.SCRIPT:
            from homeassistant.components.script.config import (  # noqa: PLC0415
                async_validate_config_item as async_validate_script,
            )

            validated = await async_validate_script(hass, source_id, config)
        else:
            return
    except ImportError:
        _LOGGER.debug("Validator for %s not available; skipping", source_type)
        return
    except Exception as err:
        raise TransplantWriteError(
            f"{source_type} '{source_id}' would be invalid after the change: {err}"
        ) from err
    validation_error = getattr(validated, "validation_error", None)
    if validated is None or validation_error:
        raise TransplantWriteError(
            f"{source_type} '{source_id}' would be invalid after the change: "
            f"{validation_error or 'validation failed'}"
        )


async def async_write_items(
    hass: HomeAssistant, source_type: SourceType, updates: dict[str, Any]
) -> None:
    """Write new configs for several objects of one type, then reload."""
    if not updates:
        return
    if source_type is SourceType.DASHBOARD:
        dashboards = _lovelace_dashboards(hass)
        for key, config in updates.items():
            dashboard = dashboards.get(None if key == DEFAULT_DASHBOARD_ID else key)
            if dashboard is None or getattr(dashboard, "mode", None) != "storage":
                raise TransplantWriteError(f"Dashboard '{key}' is not editable")
            await dashboard.async_save(config)
        return

    path = hass.config.path(_FILES[source_type])
    data = await hass.async_add_executor_job(_read_yaml, path)
    if source_type is SourceType.SCRIPT:
        data = data if isinstance(data, dict) else {}
        for key, config in updates.items():
            if key not in data:
                raise TransplantWriteError(f"Script '{key}' no longer exists")
            data[key] = config
    else:
        data = data if isinstance(data, list) else []
        remaining = dict(updates)
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            item_key = str(item.get("id"))
            if item_key in remaining:
                data[index] = remaining.pop(item_key)
        if remaining:
            raise TransplantWriteError(
                f"{source_type} no longer exists: {', '.join(sorted(remaining))}"
            )
    await hass.async_add_executor_job(_write_yaml, path, data)
    await hass.services.async_call(_RELOAD[source_type], "reload", blocking=True)
