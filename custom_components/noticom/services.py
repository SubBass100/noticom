"""Noticom actions: play_chime, stop, reload_chimes."""

from __future__ import annotations

import logging
import uuid

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.core import callback
from homeassistant.helpers.service import (
    async_extract_config_entry_ids,
    async_set_service_schema,
)

from . import protocol
from .const import (
    ATTR_CHIME,
    CONF_NODE_ID,
    DOMAIN,
    SERVICE_PLAY_CHIME,
    SERVICE_RELOAD_CHIMES,
    SERVICE_STOP,
)
from .hub import NoticomHub

_LOGGER = logging.getLogger(__name__)

# Targets are optional: no target means every node.
PLAY_CHIME_SCHEMA = vol.Schema(
    {**cv.ENTITY_SERVICE_FIELDS, vol.Required(ATTR_CHIME): cv.string}
)
STOP_SCHEMA = vol.Schema(cv.ENTITY_SERVICE_FIELDS)


async def _target_nodes(hass: HomeAssistant, call: ServiceCall) -> list[tuple[str, str]]:
    """(node_id, title) for targeted nodes; every node if nothing is targeted."""
    targeted = any(call.data.get(k) for k in ("entity_id", "device_id", "area_id", "floor_id", "label_id"))
    entry_ids = await async_extract_config_entry_ids(call) if targeted else None
    nodes = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        if entry_ids is not None and entry.entry_id not in entry_ids:
            continue
        nodes.append((entry.data[CONF_NODE_ID], entry.title))
    return nodes


NODE_TARGET = {
    "device": [{"integration": DOMAIN}],
    "entity": [{"integration": DOMAIN}],
}


@callback
def async_update_chime_choices(hass: HomeAssistant, names: list[str]) -> None:
    """Make the Play chime action's Chime field a dropdown of current chimes.

    services.yaml can only list fixed options, so the description is
    replaced at runtime whenever the chime list changes. Custom values stay
    allowed so templates still work.
    """
    async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_PLAY_CHIME,
        {
            "name": "Play chime",
            "description": "Plays a chime on Noticom nodes. Pick nodes, or leave the target empty to play on all of them.",
            "target": NODE_TARGET,
            "fields": {
                ATTR_CHIME: {
                    "name": "Chime",
                    "description": "Which chime to play. Manage chimes in the Noticom panel.",
                    "required": True,
                    "example": names[0] if names else "doorbell",
                    "selector": {
                        "select": {
                            "options": names,
                            "custom_value": True,
                            "sort": True,
                        }
                    },
                }
            },
        },
    )


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""
    hub: NoticomHub = hass.data[DOMAIN]

    async def play_chime(call: ServiceCall) -> ServiceResponse:
        name = call.data[ATTR_CHIME]
        chime = hub.chimes.get(name)
        if chime is None:
            available = ", ".join(c.name for c in hub.chimes.chimes) or "none"
            raise ServiceValidationError(
                f"No chime named {name!r}. Available: {available}. "
                "Add WAV or MP3 files to /config/noticom/chimes/."
            )
        played, offline = [], []
        for node_id, title in await _target_nodes(hass, call):
            sent = await hub.async_send(
                node_id,
                protocol.T_PLAY,
                job_id=uuid.uuid4().hex,
                kind=protocol.KIND_CHIME,
                chime_hash=chime.hash,
            )
            (played if sent else offline).append(title)
        if offline:
            _LOGGER.info("Chime %s not played on offline nodes: %s", chime.name, ", ".join(offline))
        return {"chime": chime.name, "played": played, "offline": offline}

    async def stop(call: ServiceCall) -> None:
        for node_id, _ in await _target_nodes(hass, call):
            await hub.async_send(node_id, protocol.T_STOP)

    async def reload_chimes(call: ServiceCall) -> None:
        if await hub.chimes.async_scan():
            await hub.async_broadcast_chimes()

    hass.services.async_register(
        DOMAIN, SERVICE_PLAY_CHIME, play_chime, PLAY_CHIME_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP, stop, STOP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RELOAD_CHIMES, reload_chimes)
    async_update_chime_choices(hass, [c.name for c in hub.chimes.chimes])
