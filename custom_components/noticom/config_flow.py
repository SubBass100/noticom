"""Config flow for Noticom: discover and adopt nodes."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import protocol
from .const import (
    ADOPT_TIMEOUT_S,
    CONF_BUTTON_NC,
    CONF_BUTTON_PIN,
    CONF_NODE_ID,
    CONF_NODE_PUBKEY,
    DOMAIN,
    NODE_ADOPT_PORT,
)
from .hub import node_options
from .identity import async_get_server_key

_LOGGER = logging.getLogger(__name__)


class AdoptError(Exception):
    """Adoption failed; `reason` is a translation key."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _url_host(discovery_info: ZeroconfServiceInfo) -> str:
    """Pick the address to reach the node at, formatted for a URL.

    Prefer IPv4: a node's advertisement may also carry IPv6 link-local
    addresses, which need brackets and often aren't routable from HA.
    """
    addresses = discovery_info.ip_addresses or [discovery_info.ip_address]
    for address in addresses:
        if address.version == 4:
            return str(address)
    return f"[{addresses[0]}]"


class NoticomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle adoption of a Noticom node. One config entry per node."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Per-node settings that aren't entities (the button wiring)."""
        return NoticomOptionsFlow()

    def __init__(self) -> None:
        self._host: str | None = None
        self._node_id: str | None = None

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle an unclaimed node advertising itself."""
        node_id = discovery_info.properties.get("node_id")
        if not node_id:
            return self.async_abort(reason="invalid_discovery")
        await self.async_set_unique_id(node_id)
        self._abort_if_unique_id_configured()
        self._host = _url_host(discovery_info)
        self._node_id = node_id
        self.context["title_placeholders"] = {"node_id": node_id}
        return await self.async_step_adopt()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Nodes are added by discovery only."""
        return self.async_abort(reason="discovery_only")

    async def async_step_adopt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm, then ask the user to press the node's button."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                node_pubkey = await self._async_adopt()
            except AdoptError as err:
                errors["base"] = err.reason
            else:
                return self.async_create_entry(
                    title=f"Noticom {self._node_id}",
                    data={
                        CONF_NODE_ID: self._node_id,
                        CONF_NODE_PUBKEY: node_pubkey,
                    },
                )
        return self.async_show_form(
            step_id="adopt",
            description_placeholders={"node_id": self._node_id or ""},
            errors=errors,
        )

    async def _async_adopt(self) -> str:
        """Run the adoption handshake (docs/DESIGN.md §1); return node pubkey."""
        try:
            server_url = get_url(self.hass, allow_external=False)
        except NoURLAvailableError as err:
            raise AdoptError("no_internal_url") from err

        server_key = await async_get_server_key(self.hass)
        nonce = protocol.new_nonce()
        session = async_get_clientsession(self.hass)
        url = f"http://{self._host}:{NODE_ADOPT_PORT}/adopt"
        _LOGGER.debug("Adopting node %s at %s", self._node_id, url)
        try:
            async with session.post(
                url,
                json={
                    "server_pubkey": protocol.public_key_b64(server_key),
                    "nonce": nonce,
                    "server_url": server_url,
                },
                timeout=aiohttp.ClientTimeout(total=ADOPT_TIMEOUT_S),
            ) as resp:
                if resp.status == 408:
                    raise AdoptError("button_timeout")
                if resp.status != 200:
                    _LOGGER.warning(
                        "Node %s at %s answered HTTP %s: %s",
                        self._node_id, url, resp.status, await resp.text(),
                    )
                    raise AdoptError("cannot_connect")
                body = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning(
                "Couldn't reach node %s at %s: %r", self._node_id, url, err
            )
            raise AdoptError("cannot_connect") from err

        node_pubkey = body.get("node_pubkey", "")
        if body.get("node_id") != self._node_id or not protocol.verify(
            node_pubkey, protocol.b64d(nonce), body.get("sig", "")
        ):
            _LOGGER.warning("Node %s returned an invalid adoption reply", self._node_id)
            raise AdoptError("invalid_reply")
        return node_pubkey


class NoticomOptionsFlow(OptionsFlow):
    """Edit a node's button pin and type."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the button settings."""
        if user_input is not None:
            return self.async_create_entry(
                data={**self.config_entry.options, **user_input}
            )
        opts = node_options(self.config_entry)
        schema = vol.Schema(
            {
                vol.Required(CONF_BUTTON_PIN, default=opts[CONF_BUTTON_PIN]): vol.All(
                    vol.Coerce(int), vol.Range(min=2, max=27)
                ),
                vol.Required(CONF_BUTTON_NC, default=opts[CONF_BUTTON_NC]): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
