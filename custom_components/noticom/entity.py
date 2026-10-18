"""Base entity for a Noticom node."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .hub import node_options, signal_update


class NoticomEntity(Entity):
    """Shared device info and live updates for one node."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, key: str) -> None:
        self._entry = entry
        self._node_id: str = entry.runtime_data.node_id
        self._hub = entry.runtime_data.hub
        self._attr_unique_id = f"{self._node_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._node_id)},
            name=entry.title,
            manufacturer="Noticom",
            model="ReSpeaker 2-Mic node",
        )

    @property
    def connected(self) -> bool:
        """Whether the node is online."""
        return self._hub.is_connected(self._node_id)

    @property
    def options(self) -> dict[str, Any]:
        """This node's settings."""
        return node_options(self._entry)

    async def async_set_option(self, key: str, value: Any) -> None:
        """Change one setting; the update listener pushes it to the node."""
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, key: value}
        )
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Refresh when the node connects, disconnects or reports state."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._node_id), self.async_write_ha_state
            )
        )
