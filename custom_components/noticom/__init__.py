"""The Noticom notification and intercom integration.

Scaffold status: discovery and adoption work end to end (config_flow.py).
Still to build, in order: the node WebSocket endpoint and auth (§2 of
docs/DESIGN.md), file endpoints (§3), chime storage and the sidebar panel,
the actions in const.py, and per-node entities.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_NODE_ID, CONF_NODE_PUBKEY, DOMAIN
from .identity import async_get_server_key

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class NodeRuntime:
    """Runtime state for one adopted node."""

    node_id: str
    pubkey: str
    connected: bool = False


type NoticomConfigEntry = ConfigEntry[NodeRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration-wide pieces shared by all nodes."""
    await async_get_server_key(hass)
    # TODO: register WS and file views, load chime store, register panel
    # and actions.
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NoticomConfigEntry) -> bool:
    """Set up one adopted node."""
    entry.runtime_data = NodeRuntime(
        node_id=entry.data[CONF_NODE_ID],
        pubkey=entry.data[CONF_NODE_PUBKEY],
    )
    # TODO: forward to entity platforms once they exist.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NoticomConfigEntry) -> bool:
    """Unload a node."""
    return True
