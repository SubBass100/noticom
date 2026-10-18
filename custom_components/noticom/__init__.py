"""The Noticom notification and intercom integration.

Status: discovery, adoption and the node control channel (docs/DESIGN.md
§1-2) work. Still to build: file endpoints (§3), chime storage and the
sidebar panel, the actions in const.py, and media_player entities.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_NODE_ID, CONF_NODE_PUBKEY, DOMAIN
from .hub import NoticomHub
from .identity import async_get_server_key
from .websocket import NoticomWebSocketView

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SWITCH]


@dataclass
class NodeRuntime:
    """Runtime handles for one adopted node."""

    node_id: str
    pubkey: str
    hub: NoticomHub


type NoticomConfigEntry = ConfigEntry[NodeRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration-wide pieces shared by all nodes."""
    await async_get_server_key(hass)
    hass.data[DOMAIN] = NoticomHub(hass)
    hass.http.register_view(NoticomWebSocketView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NoticomConfigEntry) -> bool:
    """Set up one adopted node."""
    hub: NoticomHub = hass.data[DOMAIN]
    entry.runtime_data = NodeRuntime(
        node_id=entry.data[CONF_NODE_ID],
        pubkey=entry.data[CONF_NODE_PUBKEY],
        hub=hub,
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: NoticomConfigEntry) -> None:
    """Push changed settings (or a rename) to the node straight away."""
    await entry.runtime_data.hub.async_push_config(entry, entry.runtime_data.node_id)


async def async_unload_entry(hass: HomeAssistant, entry: NoticomConfigEntry) -> bool:
    """Unload a node. Its connection stays up (unload also happens on reload)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The user deleted the node: tell it to forget us, if it's online.

    If it's offline, it gets a signed unpair the next time it connects.
    """
    hub: NoticomHub | None = hass.data.get(DOMAIN)
    if hub is not None:
        await hub.async_unpair(entry.data[CONF_NODE_ID], await async_get_server_key(hass))
