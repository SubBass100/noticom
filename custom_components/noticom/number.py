"""Volume and microphone settings for Noticom nodes."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_MIC_BOOST, CONF_MIC_GAIN, CONF_VOLUME
from .entity import NoticomEntity


@dataclass(frozen=True, kw_only=True)
class NoticomNumberDescription(NumberEntityDescription):
    """A node setting backed by an entry option."""


NUMBERS = (
    NoticomNumberDescription(
        key=CONF_VOLUME,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        icon="mdi:volume-high",
    ),
    NoticomNumberDescription(
        key=CONF_MIC_GAIN,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        icon="mdi:microphone",
    ),
    NoticomNumberDescription(
        key=CONF_MIC_BOOST,
        native_min_value=0,
        native_max_value=3,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        icon="mdi:microphone-plus",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the node's settings."""
    async_add_entities(NoticomNumber(entry, d) for d in NUMBERS)


class NoticomNumber(NoticomEntity, NumberEntity):
    """A numeric node setting. Editable while the node is offline too."""

    entity_description: NoticomNumberDescription

    def __init__(self, entry, description: NoticomNumberDescription) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return self.options[self.entity_description.key]

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set_option(self.entity_description.key, int(value))
