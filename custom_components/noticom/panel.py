"""The Noticom sidebar panel and its admin-only API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import (
    KEY_HASS,
    KEY_HASS_USER,
    HomeAssistantView,
    StaticPathConfig,
)
from homeassistant.core import HomeAssistant, callback

from .chimes import MAX_UPLOAD_BYTES, ChimeError
from .const import DOMAIN
from .hub import NoticomHub

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "noticom"
STATIC_URL = "/noticom_static"
UPLOAD_PATH = "/api/noticom/panel/chimes"
PREVIEW_PATH = "/api/noticom/panel/chime/{chime_hash}"
FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Serve the panel's JS, register it in the sidebar, and add its API."""
    version = (FRONTEND_DIR / "noticom-panel.js").stat().st_mtime_ns
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="noticom-panel",
        sidebar_title="Noticom",
        sidebar_icon="mdi:bullhorn-variant",
        module_url=f"{STATIC_URL}/noticom-panel.js?v={version}",
        require_admin=True,
    )
    hass.http.register_view(ChimeUploadView())
    hass.http.register_view(ChimePreviewView())
    websocket_api.async_register_command(hass, ws_list_chimes)
    websocket_api.async_register_command(hass, ws_delete_chime)


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
