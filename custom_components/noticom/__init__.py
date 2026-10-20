"""The Noticom notification and intercom integration.

Status: discovery, adoption, the node control channel, chimes and themes,
the push-to-talk intercom, the sidebar panel, any-sound-card nodes and node
software updates work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    CHIME_SCAN_INTERVAL_S,
    CONF_MIC_BOOST,
    CONF_MIC_GAIN,
    CONF_NODE_ID,
    CONF_NODE_PUBKEY,
    CONF_PTT_ENABLED,
    DOMAIN,
    LATEST_CHECK_INTERVAL_S,
)
from .files import NoticomChimeView, NoticomClipUploadView, NoticomClipView
from .hub import NoticomHub, node_caps
from .identity import async_get_server_key
from .panel import async_setup_panel
from .services import async_setup_services
from .websocket import NoticomWebSocketView

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.UPDATE,
]


@dataclass
class NodeRuntime:
    """Runtime handles for one adopted node."""

    node_id: str
    pubkey: str
    hub: NoticomHub
    pushed: tuple = ()  # settings last sent to the node


type NoticomConfigEntry = ConfigEntry[NodeRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration-wide pieces shared by all nodes."""
    await async_get_server_key(hass)
    hub = hass.data[DOMAIN] = NoticomHub(hass)
    await hub.async_load_settings()
    await hub.chimes.async_scan()
    await hub.intercom.async_load()
    await hub.themes.async_load()

    async def _rescan(_now) -> None:
        if await hub.chimes.async_scan():
            await hub.async_broadcast_chimes()

    async_track_time_interval(hass, _rescan, timedelta(seconds=CHIME_SCAN_INTERVAL_S))
    # Check GitHub for newer node software now (in the background) and every 6 h.
    hass.async_create_background_task(hub.software.async_check_latest(), "noticom_check_latest")
    async_track_time_interval(
        hass, hub.software.async_check_latest, timedelta(seconds=LATEST_CHECK_INTERVAL_S)
    )
    hass.http.register_view(NoticomWebSocketView())
    hass.http.register_view(NoticomChimeView())
    hass.http.register_view(NoticomClipUploadView())
    hass.http.register_view(NoticomClipView())
    async_setup_services(hass)
    await async_setup_panel(hass)
    # Switch themes on schedule (checked every minute) and add the theme
    # picker and active-theme sensor.
    async_track_time_change(hass, hub.themes.check_active, second=0)
    for platform in (Platform.SELECT, Platform.SENSOR):
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {"themes": True}, config)
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NoticomConfigEntry) -> bool:
    """Set up one adopted node."""
    hub: NoticomHub = hass.data[DOMAIN]
    entry.runtime_data = NodeRuntime(
        node_id=entry.data[CONF_NODE_ID],
        pubkey=entry.data[CONF_NODE_PUBKEY],
        hub=hub,
    )
    entry.runtime_data.pushed = _pushed_settings(entry)
    _remove_unsupported_entities(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _remove_unsupported_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop mic/PTT entities a node's hardware no longer supports."""
    caps = node_caps(entry)
    node_id = entry.data[CONF_NODE_ID]
    unwanted = []
    if not caps["mic"]:
        unwanted.append(("number", CONF_MIC_GAIN))
    if not caps["mic_boost"]:
        unwanted.append(("number", CONF_MIC_BOOST))
    if not (caps["mic"] and caps["button"]):
        unwanted.append(("switch", CONF_PTT_ENABLED))
    registry = er.async_get(hass)
    for platform, key in unwanted:
        if entity_id := registry.async_get_entity_id(platform, DOMAIN, f"{node_id}_{key}"):
            registry.async_remove(entity_id)


def _pushed_settings(entry: ConfigEntry) -> tuple:
    """What a node's config depends on (entry data changes, like its reported
    version or hardware, don't need a push)."""
    return (entry.title, tuple(sorted((k, repr(v)) for k, v in entry.options.items())))


async def _async_options_updated(hass: HomeAssistant, entry: NoticomConfigEntry) -> None:
    """Push changed settings (or a rename) to the node straight away."""
    runtime = entry.runtime_data
    if (settings := _pushed_settings(entry)) == runtime.pushed:
        return
    runtime.pushed = settings
    await runtime.hub.async_push_config(entry, runtime.node_id)


async def async_unload_entry(hass: HomeAssistant, entry: NoticomConfigEntry) -> bool:
    """Unload a node. Its connection stays up (unload also happens on reload)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The user deleted the node: tell it to forget us, if it's online.

    If it's offline, it gets a signed unpair the next time it connects.
    """
    hub: NoticomHub | None = hass.data.get(DOMAIN)
    if hub is not None:
        await hub.async_unpair(entry.data[CONF_NODE_ID], await async_get_server_key(hass))
