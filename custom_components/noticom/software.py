"""Node software versions: what's newest, what each node runs, updating."""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

import aiohttp
from awesomeversion import AwesomeVersion, AwesomeVersionException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from . import protocol
from .const import (
    CONF_NODE_ID,
    DOMAIN,
    INSTALL_COMMAND,
    KNOWN_NODE_VERSION,
    MIN_REMOTE_UPDATE_VERSION,
    NODE_UPDATE_REF,
    NODE_VERSION_URL,
    UPDATE_TIMEOUT_S,
)

if TYPE_CHECKING:
    from .hub import NoticomHub

_LOGGER = logging.getLogger(__name__)

SIGNAL_SOFTWARE = f"{DOMAIN}_software"
CONF_SW_VERSION = "sw_version"
_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def newer(candidate: str | None, current: str | None) -> bool:
    """Whether `candidate` is a newer version than `current`."""
    if not candidate or not current:
        return False
    try:
        return AwesomeVersion(candidate) > AwesomeVersion(current)
    except AwesomeVersionException:
        return False


class NodeSoftware:
    """Tracks the newest node version and node updates in progress."""

    def __init__(self, hass: HomeAssistant, hub: NoticomHub) -> None:
        self.hass = hass
        self.hub = hub
        self.latest = KNOWN_NODE_VERSION
        self._updating: dict[str, float] = {}  # node_id -> when the update started

    async def async_check_latest(self, _now=None) -> None:
        """Ask GitHub what the newest node version is (keeps the last known on failure)."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(NODE_VERSION_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Couldn't check for node updates: %r", err)
            return
        if (match := _VERSION_LINE.search(text)) and newer(match.group(1), self.latest):
            self.latest = match.group(1)
            _LOGGER.info("Noticom node software %s is available", self.latest)
            async_dispatcher_send(self.hass, SIGNAL_SOFTWARE)

    def installed(self, entry: ConfigEntry) -> str | None:
        """The version a node runs (live if connected, else last seen)."""
        link = self.hub.links.get(entry.data[CONF_NODE_ID])
        if link is not None and link.version:
            return link.version
        return entry.data.get(CONF_SW_VERSION)

    def update_available(self, entry: ConfigEntry) -> bool:
        return newer(self.latest, self.installed(entry))

    def can_update_remotely(self, entry: ConfigEntry) -> bool:
        """Old nodes don't understand the update command: they need one SSH update."""
        installed = self.installed(entry)
        return bool(installed) and not newer(MIN_REMOTE_UPDATE_VERSION, installed)

    def in_progress(self, node_id: str) -> bool:
        started = self._updating.get(node_id)
        if started is None:
            return False
        if time.monotonic() - started > UPDATE_TIMEOUT_S:
            del self._updating[node_id]
            return False
        return True

    async def async_update(self, node_id: str) -> None:
        """Tell a node to install the newest version. Raises if it can't."""
        if not self.hub.is_connected(node_id):
            raise HomeAssistantError("The node is offline, so it can't be updated right now.")
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, node_id)
        if entry is not None and not self.can_update_remotely(entry):
            raise HomeAssistantError(
                f"{entry.title} runs an older version that can't update itself from Home "
                f"Assistant yet. Update it once over SSH with: {INSTALL_COMMAND}"
            )
        if not await self.hub.async_send(node_id, protocol.T_UPDATE, ref=NODE_UPDATE_REF):
            raise HomeAssistantError("Couldn't reach the node to start the update.")
        self._updating[node_id] = time.monotonic()
        async_dispatcher_send(self.hass, SIGNAL_SOFTWARE)

    @callback
    def node_connected(self, entry: ConfigEntry, version: str) -> None:
        """A node (re)connected: remember its version; an update may have finished."""
        node_id = entry.data[CONF_NODE_ID]
        if version and entry.data.get(CONF_SW_VERSION) != version:
            if node_id in self._updating:
                _LOGGER.info("Node %s is now on version %s", entry.title, version)
            self._updating.pop(node_id, None)
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_SW_VERSION: version}
            )
        device = dr.async_get(self.hass).async_get_device({(DOMAIN, node_id)})
        if device is not None and version and device.sw_version != version:
            dr.async_get(self.hass).async_update_device(device.id, sw_version=version)
        async_dispatcher_send(self.hass, SIGNAL_SOFTWARE)

    @callback
    def node_state(self, entry: ConfigEntry, updating: str | None, error: str | None) -> None:
        """A node reported its update status."""
        node_id = entry.data[CONF_NODE_ID]
        if error:
            _LOGGER.warning("Node %s couldn't update: %s", entry.title, error)
            self._updating.pop(node_id, None)
            async_dispatcher_send(self.hass, SIGNAL_SOFTWARE)
