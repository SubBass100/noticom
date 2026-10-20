"""Integration-wide state: live node connections and per-node config."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from . import protocol
from .chimes import ChimeStore
from .const import (
    CONF_BUTTON_NC,
    CONF_BUTTON_PIN,
    CONF_CAPS,
    CONF_INTERCOM_TARGETS,
    CONF_OUTPUT_DEVICE,
    CONF_MIC_BOOST,
    CONF_MIC_GAIN,
    CONF_PTT_ENABLED,
    CONF_VOLUME,
    DEFAULT_BUTTON_NC,
    DEFAULT_BUTTON_PIN,
    DEFAULT_CHIME_PRIORITY,
    DEFAULT_MIC_BOOST,
    DEFAULT_MIC_GAIN,
    DEFAULT_PTT_ENABLED,
    DEFAULT_VOLUME,
    DOMAIN,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Nodes from before capabilities were reported are ReSpeaker nodes with a button.
CAPS_DEFAULTS: dict[str, Any] = {"mic": True, "mic_boost": True, "button": True, "outputs": []}


def node_caps(entry: ConfigEntry) -> dict[str, Any]:
    """What the node's hardware can do, as last reported."""
    return {**CAPS_DEFAULTS, **entry.data.get(CONF_CAPS, {})}


def entity_shape(caps: dict[str, Any]) -> tuple[bool, bool, bool]:
    """The capabilities that decide which entities a node has."""
    return (bool(caps.get("mic")), bool(caps.get("mic_boost")), bool(caps.get("button")))


OPTION_DEFAULTS: dict[str, Any] = {
    CONF_VOLUME: DEFAULT_VOLUME,
    CONF_MIC_GAIN: DEFAULT_MIC_GAIN,
    CONF_MIC_BOOST: DEFAULT_MIC_BOOST,
    CONF_PTT_ENABLED: DEFAULT_PTT_ENABLED,
    CONF_BUTTON_PIN: DEFAULT_BUTTON_PIN,
    CONF_BUTTON_NC: DEFAULT_BUTTON_NC,
}


def signal_update(node_id: str) -> str:
    """Dispatcher signal fired when a node's connection or state changes."""
    return f"{DOMAIN}_{node_id}_update"


def node_options(entry: ConfigEntry) -> dict[str, Any]:
    """Entry options merged over defaults."""
    return {**OPTION_DEFAULTS, **entry.options}


def node_config(entry: ConfigEntry, chime_priority: bool = DEFAULT_CHIME_PRIORITY) -> dict[str, Any]:
    """The config object sent to a node (docs/DESIGN.md §2)."""
    opts = node_options(entry)
    return {
        "name": entry.title,
        "volume": opts[CONF_VOLUME],
        "mic_gain": opts[CONF_MIC_GAIN],
        "mic_boost": opts[CONF_MIC_BOOST],
        "ptt_enabled": opts[CONF_PTT_ENABLED],
        "button_pin": opts[CONF_BUTTON_PIN],
        "button_nc": opts[CONF_BUTTON_NC],
        "chime_priority": chime_priority,
        "output_device": opts.get(CONF_OUTPUT_DEVICE, "auto"),
        "input_device": "auto",
    }


@dataclass
class NodeLink:
    """One authenticated WebSocket connection from a node."""

    node_id: str
    ws: web.WebSocketResponse
    node_nonce: str  # the node's handshake nonce; binds signed unpair messages
    version: str = ""
    state: dict[str, Any] = field(default_factory=dict)

    async def send(self, msg_type: str, **fields: Any) -> bool:
        """Send a message; False if the socket is gone."""
        if self.ws.closed:
            return False
        try:
            await self.ws.send_str(protocol.encode(msg_type, **fields))
        except ConnectionError:
            return False
        return True


class NoticomHub:
    """Tracks which nodes are connected."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.links: dict[str, NodeLink] = {}
        self.chimes = ChimeStore(hass)
        self._settings_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.settings"
        )
        self.settings: dict[str, Any] = {}
        from .intercom import Intercom  # noqa: PLC0415 - avoids an import cycle

        self.intercom = Intercom(hass, self)
        from .software import NodeSoftware  # noqa: PLC0415

        self.software = NodeSoftware(hass, self)
        from .themes import ThemeStore  # noqa: PLC0415

        self.themes = ThemeStore(hass, self)

    async def async_load_settings(self) -> None:
        """Load integration-wide settings."""
        self.settings = await self._settings_store.async_load() or {}

    async def async_save_settings(self) -> None:
        """Persist integration-wide settings."""
        await self._settings_store.async_save(self.settings)

    @property
    def chime_priority(self) -> bool:
        """Whether chimes go ahead of waiting intercom messages."""
        return bool(self.settings.get("chime_priority", DEFAULT_CHIME_PRIORITY))

    @property
    def node_defaults(self) -> dict[str, Any]:
        """Settings given to newly adopted nodes."""
        return {
            **OPTION_DEFAULTS,
            CONF_INTERCOM_TARGETS: "all",
            **self.settings.get("node_defaults", {}),
        }

    async def async_push_config_all(self) -> None:
        """Re-send every connected node its config (after a global change)."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await self.async_push_config(entry, entry.data["node_id"])

    async def async_broadcast_chimes(self) -> None:
        """Send the current sound library to every connected node.

        (The protocol calls these "chimes": nodes keep every sound, so a theme
        switch never waits for a download.)
        """
        manifest = self.chimes.manifest()
        for link in list(self.links.values()):
            await link.send(protocol.T_CHIMES, chimes=manifest)

    def is_connected(self, node_id: str) -> bool:
        """Whether a node has a live, authenticated connection."""
        link = self.links.get(node_id)
        return link is not None and not link.ws.closed

    @callback
    def attach(self, link: NodeLink) -> NodeLink | None:
        """Register a new connection; return a replaced older one, if any."""
        old = self.links.get(link.node_id)
        self.links[link.node_id] = link
        async_dispatcher_send(self.hass, signal_update(link.node_id))
        return old

    @callback
    def detach(self, link: NodeLink) -> None:
        """Forget a connection, unless a newer one already replaced it."""
        if self.links.get(link.node_id) is link:
            del self.links[link.node_id]
            async_dispatcher_send(self.hass, signal_update(link.node_id))

    @callback
    def update_state(self, link: NodeLink, state: dict[str, Any]) -> None:
        """Store a node's reported state."""
        if isinstance(caps := state.pop("caps", None), dict):
            self.async_update_caps(link.node_id, caps)
        updating, error = state.pop("updating", None), state.pop("update_error", None)
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, link.node_id)
        if entry is not None:
            self.software.node_state(entry, updating, error)
        link.state.update(state)
        async_dispatcher_send(self.hass, signal_update(link.node_id))

    @callback
    def async_update_caps(self, node_id: str, caps: dict[str, Any]) -> None:
        """Remember a node's capabilities; reload it if its entities change."""
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, node_id)
        if entry is None or not caps or entry.data.get(CONF_CAPS) == caps:
            return
        before = entity_shape(node_caps(entry))
        self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_CAPS: caps})
        if entity_shape(node_caps(entry)) != before:
            _LOGGER.info("Node %s hardware changed; updating its entities", entry.title)
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        else:
            async_dispatcher_send(self.hass, signal_update(node_id))

    async def async_send(self, node_id: str, msg_type: str, **fields: Any) -> bool:
        """Send to a node if it's connected."""
        link = self.links.get(node_id)
        return bool(link and await link.send(msg_type, **fields))

    async def async_push_config(self, entry: ConfigEntry, node_id: str) -> bool:
        """Send a node its current config."""
        return await self.async_send(
            node_id, protocol.T_CONFIG, config=node_config(entry, self.chime_priority)
        )

    async def async_unpair(self, node_id: str, server_key: Any) -> bool:
        """Tell a connected node to forget this server, then drop it."""
        link = self.links.get(node_id)
        if link is None:
            return False
        sig = protocol.sign(server_key, protocol.unpair_payload(link.node_nonce))
        sent = await link.send(protocol.T_UNPAIR, sig=sig)
        await link.ws.close()
        return sent
