"""The integration-wide active theme sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .theme_entities import NoticomThemeEntity, active_theme_attributes


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None) -> None:
    """Loaded once from async_setup."""
    if discovery_info is None:
        return
    async_add_entities([NoticomActiveThemeSensor(hass.data[DOMAIN].themes)])


class NoticomActiveThemeSensor(NoticomThemeEntity, SensorEntity):
    """The theme playing right now."""

    _attr_name = "Noticom active theme"
    _attr_icon = "mdi:palette"

    def __init__(self, themes) -> None:
        super().__init__(themes, "active_theme")

    @property
    def native_value(self) -> str:
        return self._themes.active()[0]["name"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return active_theme_attributes(self._themes)
