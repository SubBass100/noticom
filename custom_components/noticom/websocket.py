"""The node control channel: GET /api/noticom/ws (docs/DESIGN.md §2)."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import WSMsgType, web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import CoreState

from . import protocol
from .const import CONF_NODE_PUBKEY, DOMAIN, WS_PATH
from .hub import NodeLink, NoticomHub, node_config
from .identity import async_get_server_key

_LOGGER = logging.getLogger(__name__)

AUTH_TIMEOUT_S = 10
HEARTBEAT_S = 30


def _adoption_in_progress(hass, node_id: str) -> bool:
    """Whether a config flow for this node hasn't finished yet."""
    return any(
        flow.get("context", {}).get("unique_id") == node_id
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    )


class NoticomWebSocketView(HomeAssistantView):
    """Accepts node connections; auth is the node's Ed25519 key, not HA users."""

    url = WS_PATH
    name = "api:noticom:ws"
    requires_auth = False

    async def get(self, request: web.Request) -> web.WebSocketResponse:
        """Handle one node connection for its lifetime."""
        hass = request.app[KEY_HASS]
        hub: NoticomHub = hass.data[DOMAIN]
        ws = web.WebSocketResponse(heartbeat=HEARTBEAT_S)
        await ws.prepare(request)

        link = await self._handshake(hass, ws)
        if link is None:
            await ws.close()
            return ws

        if (old := hub.attach(link)) is not None:
            await old.ws.close()  # the node reconnected; drop the stale socket
        _LOGGER.info("Node %s connected (v%s)", link.node_id, link.version)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = protocol.decode(msg.data)
                except ValueError:
                    _LOGGER.debug("Node %s sent invalid message", link.node_id)
                    continue
                self._handle(hub, link, data)
        finally:
            hub.detach(link)
            _LOGGER.info("Node %s disconnected", link.node_id)
        return ws

    async def _handshake(self, hass, ws: web.WebSocketResponse) -> NodeLink | None:
        """Mutual auth. Returns the link, or None after telling the node why."""
        nonce = protocol.new_nonce()
        await ws.send_str(protocol.encode(protocol.T_CHALLENGE, nonce=nonce))
        try:
            msg = await ws.receive(timeout=AUTH_TIMEOUT_S)
            data = protocol.decode(msg.data) if msg.type == WSMsgType.TEXT else {}
        except (TimeoutError, asyncio.CancelledError, ValueError):
            return None
        node_id = data.get("node_id")
        node_nonce = data.get("nonce")
        if data.get("t") != protocol.T_AUTH or not node_id or not node_nonce:
            await ws.send_str(protocol.encode(protocol.T_ERROR, reason="bad_auth"))
            return None

        server_key = await async_get_server_key(hass)
        entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, node_id)
        if entry is None:
            if _adoption_in_progress(hass, node_id):
                # Just adopted; the entry is being created. Ask it to retry.
                await ws.send_str(protocol.encode(protocol.T_ERROR, reason="not_ready"))
                return None
            # Not ours (any more). If HA is fully up, the node was removed while
            # it was offline: tell it, signed so it knows the message is ours.
            if hass.state is CoreState.running:
                _LOGGER.info("Unknown node %s connected; telling it to unpair", node_id)
                try:
                    sig = protocol.sign(server_key, protocol.unpair_payload(node_nonce))
                except ValueError:
                    return None
                await ws.send_str(protocol.encode(protocol.T_UNPAIR, sig=sig))
            return None

        if not protocol.verify(
            entry.data[CONF_NODE_PUBKEY], protocol.b64d(nonce), data.get("sig", "")
        ):
            _LOGGER.warning("Node %s failed authentication", node_id)
            await ws.send_str(protocol.encode(protocol.T_ERROR, reason="bad_signature"))
            return None
        if entry.state is not ConfigEntryState.LOADED:
            await ws.send_str(protocol.encode(protocol.T_ERROR, reason="not_ready"))
            return None

        try:
            server_sig = protocol.sign(server_key, protocol.b64d(node_nonce))
        except ValueError:
            return None
        link = NodeLink(
            node_id=node_id, ws=ws, node_nonce=node_nonce, version=data.get("version", "")
        )
        await ws.send_str(
            protocol.encode(
                protocol.T_WELCOME,
                sig=server_sig,
                config=node_config(entry),
                chimes=hass.data[DOMAIN].chimes.manifest(),
            )
        )
        return link

    def _handle(self, hub: NoticomHub, link: NodeLink, data: dict) -> None:
        """Dispatch one message from an authenticated node."""
        msg_type = data["t"]
        if msg_type == protocol.T_STATE:
            hub.update_state(
                link, {k: v for k, v in data.items() if k != "t"}
            )
        elif msg_type == protocol.T_CONFIG_RESULT:
            if data.get("ok"):
                _LOGGER.debug("Node %s applied config", link.node_id)
            else:
                _LOGGER.warning(
                    "Node %s couldn't apply config: %s", link.node_id, data.get("reason")
                )
        elif msg_type == protocol.T_JOB:
            status = data.get("status")
            log = _LOGGER.debug if status in ("started", "done") else _LOGGER.info
            log("Node %s job %s: %s", link.node_id, data.get("job_id"), status)
        else:
            _LOGGER.debug("Node %s sent unhandled %s", link.node_id, msg_type)
