"""Find which automations and scripts play which chimes.

Reads each automation's and script's configuration (as written in the UI or
YAML) and looks for noticom.play_chime actions anywhere inside it, including
inside choose/if/repeat blocks. Computed on demand, so it's always current.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN, SERVICE_PLAY_CHIME

_LOGGER = logging.getLogger(__name__)

PLAY_ACTION = f"{DOMAIN}.{SERVICE_PLAY_CHIME}"
DYNAMIC = None  # chime chosen by a template


def _chimes_in(config: Any) -> list[str | None]:
    """Chime names played anywhere in a config tree (None: a template)."""
    found: list[str | None] = []
    stack = [config]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            action = item.get("action", item.get("service"))
            if isinstance(action, str) and action.strip().lower() == PLAY_ACTION:
                data = item.get("data") or item.get("data_template") or {}
                chime = data.get("chime") if isinstance(data, dict) else None
                if isinstance(chime, str) and "{" not in chime:
                    found.append(chime.strip())
                elif isinstance(data, dict) and isinstance(data.get("sound"), str):
                    found.append("sound:" + data["sound"].strip())
                else:
                    found.append(DYNAMIC)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def _entities(hass: HomeAssistant, domain: str) -> list[Any]:
    component = hass.data.get(domain)
    entities = getattr(component, "entities", None)
    return list(entities) if entities is not None else []


def find_usage(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Every automation/script that plays a chime.

    [{"kind", "name", "entity_id", "edit", "chimes": [name | None]}]
    """
    result = []
    for kind in ("automation", "script"):
        for entity in _entities(hass, kind):
            raw = getattr(entity, "raw_config", None)
            if not raw:
                continue
            try:
                chimes = _chimes_in(raw)
            except Exception:  # noqa: BLE001 - never break the panel on odd configs
                _LOGGER.debug("Couldn't scan %s", entity.entity_id, exc_info=True)
                continue
            if not chimes:
                continue
            edit = None
            if kind == "automation" and raw.get("id"):
                edit = f"/config/automation/edit/{raw['id']}"
            elif kind == "script":
                edit = f"/config/script/edit/{entity.entity_id.split('.', 1)[1]}"
            result.append(
                {
                    "kind": kind,
                    "name": raw.get("alias") or entity.name or entity.entity_id,
                    "entity_id": entity.entity_id,
                    "edit": edit,
                    "chimes": list(dict.fromkeys(chimes)),
                }
            )
    result.sort(key=lambda u: str(u["name"]).lower())
    return result
