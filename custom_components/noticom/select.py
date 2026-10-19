"""Sound output picker for Noticom nodes."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_OUTPUT_DEVICE
from .entity import NoticomEntity
from .hub import node_caps

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
