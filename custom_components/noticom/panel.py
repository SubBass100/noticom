"""The Noticom sidebar panel and its admin-only API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import (
    KEY_HASS,
    KEY_HASS_USER,
    HomeAssistantView,
    StaticPathConfig,
)
from homeassistant.core import HomeAssistant, callback

from homeassistant.config_entries import ConfigEntryState

from .chimes import MAX_UPLOAD_BYTES, ChimeError
from .const import CONF_INTERCOM_TARGETS, CONF_NODE_ID, CONF_PTT_ENABLED, DOMAIN
from .hub import NoticomHub, node_options
from .intercom import TARGETS_ALL

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "noticom"
STATIC_URL = "/noticom_static"
UPLOAD_PATH = "/api/noticom/panel/chimes"
PREVIEW_PATH = "/api/noticom/panel/chime/{chime_hash}"
CLIP_PREVIEW_PATH = "/api/noticom/panel/clip/{clip_id}"
FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Serve the panel's JS, register it in the sidebar, and add its API."""
    version = (FRONTEND_DIR / "noticom-panel.js").stat().st_mtime_ns
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
    )
    # Load the Noticom icon set on every page so the sidebar can show it.
    icons_version = (FRONTEND_DIR / "noticom-icons.js").stat().st_mtime_ns
    sidebar_icon = "mdi:bullhorn-variant"
    try:
        frontend.add_extra_js_url(hass, f"{STATIC_URL}/noticom-icons.js?v={icons_version}")
        sidebar_icon = "noticom:logo"
    except KeyError:  # frontend not loaded (e.g. in tests): keep the stock icon
        _LOGGER.debug("Frontend not loaded; using the default sidebar icon")
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="noticom-panel",
        sidebar_title="Noticom",
        sidebar_icon=sidebar_icon,
        module_url=f"{STATIC_URL}/noticom-panel.js?v={version}",
        require_admin=True,
    )
    hass.http.register_view(ChimeUploadView())
    hass.http.register_view(ChimePreviewView())
    hass.http.register_view(ClipPreviewView())
    websocket_api.async_register_command(hass, ws_list_chimes)
    websocket_api.async_register_command(hass, ws_delete_chime)
    websocket_api.async_register_command(hass, ws_intercom_get)
    websocket_api.async_register_command(hass, ws_intercom_set_chime)
    websocket_api.async_register_command(hass, ws_intercom_set_targets)
    websocket_api.async_register_command(hass, ws_settings_get)
    websocket_api.async_register_command(hass, ws_settings_set)


def chime_list(hub: NoticomHub) -> list[dict[str, Any]]:
    """Chimes as the panel shows them."""
    return [
        {
            "name": c.name,
            "hash": c.hash,
            "duration": c.duration,
            "file": c.source.name,
        }
        for c in hub.chimes.chimes
    ]


def _require_admin(request: web.Request) -> web.Response | None:
    user = request.get(KEY_HASS_USER)
    if user is None or not user.is_admin:
        return web.json_response({"error": "Admin only."}, status=403)
    return None


class ChimeUploadView(HomeAssistantView):
    """POST multipart (file, name, replace) to add a chime."""

    url = UPLOAD_PATH
    name = "api:noticom:panel:chimes"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        if (denied := _require_admin(request)) is not None:
            return denied
        hass = request.app[KEY_HASS]
        hub: NoticomHub = hass.data[DOMAIN]
        fields: dict[str, str] = {}
        filename, data = "", b""
        try:
            reader = await request.multipart()
            while (part := await reader.next()) is not None:
                if part.name == "file":
                    filename = part.filename or ""
                    data = await part.read(decode=False)
                    if len(data) > MAX_UPLOAD_BYTES:
                        break
                elif part.name:
                    fields[part.name] = await part.text()
        except (ValueError, AssertionError):
            return web.json_response({"error": "Bad upload."}, status=400)
        if not data:
            return web.json_response({"error": "Choose a file to upload."}, status=400)
        name = fields.get("name") or Path(filename).stem
        try:
            chime = await hub.chimes.async_add(
                name, filename, data, replace=fields.get("replace") == "true"
            )
        except ChimeError as err:
            return web.json_response({"error": str(err)}, status=400)
        await hub.async_broadcast_chimes()
        _LOGGER.info("Chime %s uploaded", chime.name)
        return web.json_response({"chime": chime.name, "chimes": chime_list(hub)})


class ChimePreviewView(HomeAssistantView):
    """GET a chime's normalized WAV for the panel's preview button."""

    url = PREVIEW_PATH
    name = "api:noticom:panel:chime"
    requires_auth = True

    async def get(self, request: web.Request, chime_hash: str) -> web.StreamResponse:
        if (denied := _require_admin(request)) is not None:
            return denied
        path = request.app[KEY_HASS].data[DOMAIN].chimes.path_for_hash(chime_hash)
        if path is None:
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Content-Type": "audio/wav"})


@websocket_api.websocket_command({vol.Required("type"): "noticom/chimes/list"})
@websocket_api.require_admin
@callback
def ws_list_chimes(hass: HomeAssistant, connection, msg: dict) -> None:
    """List chimes."""
    connection.send_result(msg["id"], {"chimes": chime_list(hass.data[DOMAIN])})


@websocket_api.websocket_command(
    {vol.Required("type"): "noticom/chimes/delete", vol.Required("name"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_delete_chime(hass: HomeAssistant, connection, msg: dict) -> None:
    """Delete a chime."""
    hub: NoticomHub = hass.data[DOMAIN]
    try:
        await hub.chimes.async_delete(msg["name"])
    except ChimeError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    await hub.async_broadcast_chimes()
    _LOGGER.info("Chime %s deleted", msg["name"])
    connection.send_result(msg["id"], {"chimes": chime_list(hub)})


class ClipPreviewView(HomeAssistantView):
    """GET a recent intercom message for the panel's play button."""

    url = CLIP_PREVIEW_PATH
    name = "api:noticom:panel:clip"
    requires_auth = True

    async def get(self, request: web.Request, clip_id: str) -> web.Response:
        if (denied := _require_admin(request)) is not None:
            return denied
        clip = request.app[KEY_HASS].data[DOMAIN].intercom.get(clip_id)
        if clip is None:
            return web.Response(status=404)
        return web.Response(body=clip.data, content_type="audio/wav")


def intercom_state(hass: HomeAssistant) -> dict[str, Any]:
    """Everything the Intercom tab shows."""
    hub: NoticomHub = hass.data[DOMAIN]
    nodes = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        opts = node_options(entry)
        node_id = entry.data[CONF_NODE_ID]
        nodes.append(
            {
                "node_id": node_id,
                "name": entry.title,
                "connected": hub.is_connected(node_id),
                "ptt_enabled": opts[CONF_PTT_ENABLED],
                "targets": entry.options.get(CONF_INTERCOM_TARGETS, TARGETS_ALL),
            }
        )
    nodes.sort(key=lambda n: n["name"].lower())
    return {
        "chime": hub.intercom.chime_name,
        "chimes": [c.name for c in hub.chimes.chimes],
        "nodes": nodes,
        "messages": hub.intercom.recent(),
    }


@websocket_api.websocket_command({vol.Required("type"): "noticom/intercom/get"})
@websocket_api.require_admin
@callback
def ws_intercom_get(hass: HomeAssistant, connection, msg: dict) -> None:
    """Intercom settings, nodes and recent messages."""
    connection.send_result(msg["id"], intercom_state(hass))


@websocket_api.websocket_command(
    {vol.Required("type"): "noticom/intercom/set_chime", vol.Required("chime"): vol.Any(None, str)}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_intercom_set_chime(hass: HomeAssistant, connection, msg: dict) -> None:
    """Choose the chime played before intercom messages (null for none)."""
    hub: NoticomHub = hass.data[DOMAIN]
    name = msg["chime"]
    if name is not None:
        chime = hub.chimes.get(name)
        if chime is None:
            connection.send_error(msg["id"], "not_found", f"No chime named {name!r}.")
            return
        name = chime.name
    await hub.intercom.async_set_chime(name)
    connection.send_result(msg["id"], intercom_state(hass))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "noticom/intercom/set_targets",
        vol.Required("node_id"): str,
        vol.Required("targets"): vol.Any(TARGETS_ALL, [str]),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_intercom_set_targets(hass: HomeAssistant, connection, msg: dict) -> None:
    """Set which nodes a node's button talks to ("all" or a list of node ids)."""
    entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, msg["node_id"])
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No such node.")
        return
    targets = msg["targets"]
    if targets != TARGETS_ALL:
        known = {e.data[CONF_NODE_ID] for e in hass.config_entries.async_entries(DOMAIN)}
        targets = sorted(set(targets) & known - {msg["node_id"]})
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_INTERCOM_TARGETS: targets}
    )
    connection.send_result(msg["id"], intercom_state(hass))


NODE_DEFAULTS_SCHEMA = vol.Schema(
    {
        vol.Required("volume"): vol.All(int, vol.Range(min=0, max=100)),
        vol.Required("mic_gain"): vol.All(int, vol.Range(min=0, max=100)),
        vol.Required("mic_boost"): vol.All(int, vol.Range(min=0, max=3)),
        vol.Required("ptt_enabled"): bool,
        vol.Required("button_pin"): vol.All(int, vol.Range(min=2, max=27)),
        vol.Required("button_nc"): bool,
        vol.Required("intercom_targets"): vol.Any(TARGETS_ALL, vol.All([str], vol.Length(max=0))),
    }
)


def settings_state(hub: NoticomHub) -> dict[str, Any]:
    """Integration-wide settings shown on the Settings tab."""
    defaults = hub.node_defaults
    return {
        "chime_priority": hub.chime_priority,
        "node_defaults": {str(k): defaults[str(k)] for k in NODE_DEFAULTS_SCHEMA.schema},
    }


@websocket_api.websocket_command({vol.Required("type"): "noticom/settings/get"})
@websocket_api.require_admin
@callback
def ws_settings_get(hass: HomeAssistant, connection, msg: dict) -> None:
    """Global settings and defaults for new nodes."""
    connection.send_result(msg["id"], settings_state(hass.data[DOMAIN]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "noticom/settings/set",
        vol.Optional("chime_priority"): bool,
        vol.Optional("node_defaults"): NODE_DEFAULTS_SCHEMA,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_settings_set(hass: HomeAssistant, connection, msg: dict) -> None:
    """Save global settings; a chime-priority change reaches nodes immediately."""
    hub: NoticomHub = hass.data[DOMAIN]
    priority_changed = False
    if "chime_priority" in msg:
        priority_changed = msg["chime_priority"] != hub.chime_priority
        hub.settings["chime_priority"] = msg["chime_priority"]
    if "node_defaults" in msg:
        hub.settings["node_defaults"] = dict(msg["node_defaults"])
    await hub.async_save_settings()
    if priority_changed:
        await hub.async_push_config_all()
    connection.send_result(msg["id"], settings_state(hub))
