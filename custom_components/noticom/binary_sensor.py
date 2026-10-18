"""Connectivity sensor for Noticom nodes."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import NoticomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the node's connectivity sensor."""
    async_add_entities([NoticomConnectedSensor(entry)])


class NoticomConnectedSensor(NoticomEntity, BinarySensorEntity):
    """On while the node holds an authenticated connection to HA."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry) -> None:
        super().__init__(entry, "connected")

    @property
    def is_on(self) -> bool:
        return self.connected
