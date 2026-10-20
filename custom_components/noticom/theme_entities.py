"""Integration-wide theme entities (not tied to a node).

- select.noticom_theme: Automatic (follow the schedule) or force a theme.
- sensor.noticom_active_theme: the theme playing right now, and why.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .themes import MODE_AUTO, SIGNAL_THEMES, ThemeStore

AUTOMATIC = "Automatic"


class NoticomThemeEntity(Entity):
    """Follows theme changes."""

    _attr_should_poll = False

    def __init__(self, themes: ThemeStore, key: str) -> None:
        self._themes = themes
        self._attr_unique_id = f"{DOMAIN}_{key}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_THEMES, self.async_write_ha_state)
        )


def theme_mode_options(themes: ThemeStore) -> list[str]:
    """Automatic, then every theme by name."""
    return [AUTOMATIC, *(t["name"] for t in themes.all_themes())]


def theme_mode_current(themes: ThemeStore) -> str:
    """The select's state."""
    if themes.mode == MODE_AUTO:
        return AUTOMATIC
    try:
        return themes.theme(themes.mode)["name"]
    except Exception:  # noqa: BLE001
        return AUTOMATIC


def active_theme_attributes(themes: ThemeStore) -> dict[str, Any]:
    """Why the active theme is active."""
    theme, reason, rng = themes.active()
    attrs: dict[str, Any] = {"reason": reason, "theme_id": theme["id"]}
    if rng:
        attrs["scheduled"] = f"{rng['start']} to {rng['end']}" + (
            f", {rng['from']}-{rng['to']}" if rng.get("from") else ""
        )
    return attrs
