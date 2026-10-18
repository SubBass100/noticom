"""File endpoints for nodes, authenticated by signed requests (DESIGN §3)."""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from . import protocol
from .hub import node_options
from .intercom import MAX_CLIP_BYTES, ClipError
from .const import (
    CHIME_PATH,
    CLIP_PATH,
    CLIP_UPLOAD_PATH,
    CONF_NODE_PUBKEY,
    CONF_PTT_ENABLED,
    DOMAIN,
    HDR_NODE,
    HDR_SIG,
    HDR_TIME,
    MAX_REQUEST_AGE_S,
)

_LOGGER = logging.getLogger(__name__)


def verify_node_request(hass, request: web.Request) -> str | None:
    """Return the node id if the request is correctly signed by an adopted node."""
    node_id = request.headers.get(HDR_NODE, "")
    entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, node_id)
    if entry is None:
        return None
    if not protocol.verify_request(
        entry.data[CONF_NODE_PUBKEY],
        request.method,
        request.path,
        request.headers.get(HDR_TIME, ""),
        request.headers.get(HDR_SIG, ""),
        max_age_s=MAX_REQUEST_AGE_S,
    ):
        return None
    return node_id


class NoticomChimeView(HomeAssistantView):
    """GET /api/noticom/chime/{chime_hash}: a normalized chime WAV."""

    url = CHIME_PATH
    name = "api:noticom:chime"
    requires_auth = False

    async def get(self, request: web.Request, chime_hash: str) -> web.StreamResponse:
        hass = request.app[KEY_HASS]
        node_id = verify_node_request(hass, request)
        if node_id is None:
            return web.Response(status=401)
        path = hass.data[DOMAIN].chimes.path_for_hash(chime_hash)
        if path is None:
            return web.Response(status=404)
        _LOGGER.debug("Node %s downloading chime %s", node_id, chime_hash[:12])
        return web.FileResponse(path, headers={"Content-Type": "audio/wav"})


class NoticomClipUploadView(HomeAssistantView):
    """POST /api/noticom/clip: a node's PTT recording (16-bit WAV body)."""

    url = CLIP_UPLOAD_PATH
    name = "api:noticom:clip:upload"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        node_id = verify_node_request(hass, request)
        if node_id is None:
            return web.Response(status=401)
        entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, node_id)
        if not node_options(entry)[CONF_PTT_ENABLED]:
            return web.json_response({"error": "push to talk is off"}, status=403)
        if request.content_length and request.content_length > MAX_CLIP_BYTES:
            return web.json_response({"error": "clip too large"}, status=413)
        data = await request.read()
        try:
            clip = await hass.data[DOMAIN].intercom.async_receive(entry, data)
        except ClipError as err:
            return web.json_response({"error": str(err)}, status=400)
        return web.json_response(
            {"clip_id": clip.id, "recipients": len(clip.deliveries)}
        )


class NoticomClipView(HomeAssistantView):
    """GET /api/noticom/clip/{clip_id}: a message, for the nodes it was sent to."""

    url = CLIP_PATH
    name = "api:noticom:clip"
    requires_auth = False

    async def get(self, request: web.Request, clip_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        node_id = verify_node_request(hass, request)
        if node_id is None:
            return web.Response(status=401)
        clip = hass.data[DOMAIN].intercom.get(clip_id)
        if clip is None or node_id not in clip.deliveries:
            return web.Response(status=404)
        return web.Response(body=clip.data, content_type="audio/wav")
