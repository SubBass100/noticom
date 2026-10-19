"""Push-to-talk enable switch for Noticom nodes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_PTT_ENABLED
from .entity import NoticomEntity
from .hub import node_caps


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the node's PTT switch, if it has a microphone and a button."""
    caps = node_caps(entry)
    if caps["mic"] and caps["button"]:
        async_add_entities([NoticomPttSwitch(entry)])


class NoticomPttSwitch(NoticomEntity, SwitchEntity):
    """Turn the node's intercom button on or off."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:account-voice"

    def __init__(self, entry) -> None:
        super().__init__(entry, CONF_PTT_ENABLED)

    @property
    def is_on(self) -> bool:
        return bool(self.options[CONF_PTT_ENABLED])

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_set_option(CONF_PTT_ENABLED, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_set_option(CONF_PTT_ENABLED, False)
