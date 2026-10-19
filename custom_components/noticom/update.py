"""Node software update entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NODE_REPO
from .entity import NoticomEntity
from .software import SIGNAL_SOFTWARE


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the node's software update entity."""
    async_add_entities([NoticomNodeUpdate(entry)])


class NoticomNodeUpdate(NoticomEntity, UpdateEntity):
    """Shows the node's software version and installs the newest one."""

    # PROGRESS: report our own in_progress (the Pi takes minutes), not just
    # the moment the install command is sent.
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_release_url = f"{NODE_REPO}/commits/main"
    _attr_title = "Noticom node"

    def __init__(self, entry) -> None:
        super().__init__(entry, "software")

    @property
    def _software(self):
        return self._hub.software

    @property
    def installed_version(self) -> str | None:
        return self._software.installed(self._entry)

    @property
    def latest_version(self) -> str | None:
        installed = self.installed_version
        latest = self._software.latest
        # Never offer a "downgrade" if a node is ahead of what we know about.
        if installed and not self._software.update_available(self._entry):
            return installed
        return latest

    @property
    def in_progress(self) -> bool:
        return self._software.in_progress(self._node_id)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        await self._software.async_update(self._node_id)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SOFTWARE, self.async_write_ha_state)
        )
