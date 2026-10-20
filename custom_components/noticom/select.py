"""Sound output picker for Noticom nodes, and the theme picker."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_OUTPUT_DEVICE, DOMAIN
from .entity import NoticomEntity
from .hub import node_caps
from .theme_entities import (
    AUTOMATIC as THEME_AUTOMATIC,
    NoticomThemeEntity,
    theme_mode_current,
    theme_mode_options,
)
from .themes import MODE_AUTO

AUTOMATIC = "Automatic"


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the node's sound output picker."""
    async_add_entities([NoticomOutputSelect(entry)])


class NoticomOutputSelect(NoticomEntity, SelectEntity):
    """Which sound card the node plays on: Automatic, or one it reported."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:speaker"

    def __init__(self, entry) -> None:
        super().__init__(entry, CONF_OUTPUT_DEVICE)

    @property
    def _outputs(self) -> list[dict]:
        return [o for o in node_caps(self._entry).get("outputs", []) if "id" in o]

    def _label(self, output: dict) -> str:
        return output.get("label") or output["id"]

    @property
    def options(self) -> list[str]:
        labels = [self._label(o) for o in self._outputs]
        current = self.options_current_label()
        if current not in labels and current != AUTOMATIC:
            labels.append(current)  # chosen card is unplugged right now
        return [AUTOMATIC, *labels]

    def options_current_label(self) -> str:
        chosen = self._entry.options.get(CONF_OUTPUT_DEVICE, "auto")
        if chosen == "auto":
            return AUTOMATIC
        for output in self._outputs:
            if output["id"] == chosen:
                return self._label(output)
        return f"{chosen} (not connected)"

    @property
    def current_option(self) -> str:
        return self.options_current_label()

    @property
    def extra_state_attributes(self) -> dict:
        caps = node_caps(self._entry)
        playing_on = next(
            (self._label(o) for o in self._outputs if o["id"] == caps.get("output")), None
        )
        return {"playing_on": playing_on}

    async def async_select_option(self, option: str) -> None:
        if option == AUTOMATIC:
            value = "auto"
        else:
            value = next(
                (o["id"] for o in self._outputs if self._label(o) == option), None
            )
            if value is None:
                return  # an unplugged card; keep the current choice
        await self.async_set_option(CONF_OUTPUT_DEVICE, value)


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None) -> None:
    """The integration-wide theme picker (loaded once from async_setup)."""
    if discovery_info is None:
        return
    async_add_entities([NoticomThemeSelect(hass.data[DOMAIN].themes)])


class NoticomThemeSelect(NoticomThemeEntity, SelectEntity):
    """Automatic (follow the schedule), or force one theme."""

    _attr_name = "Noticom theme"
    _attr_icon = "mdi:palette-outline"

    def __init__(self, themes) -> None:
        super().__init__(themes, "theme")

    @property
    def options(self) -> list[str]:
        return theme_mode_options(self._themes)

    @property
    def current_option(self) -> str:
        return theme_mode_current(self._themes)

    async def async_select_option(self, option: str) -> None:
        if option == THEME_AUTOMATIC:
            await self._themes.async_set_mode(MODE_AUTO)
            return
        for theme in self._themes.all_themes():
            if theme["name"] == option:
                await self._themes.async_set_mode(theme["id"])
                return
