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
from homeassistant.const import CONF_HOST, CONF_NAME
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
from .hub import OPTION_DEFAULTS, node_options
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


def _bracket(host: str) -> str:
    """Wrap a bare IPv6 address in brackets for use in a URL."""
    host = host.strip()
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


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
        """Add a node by IP address, for when discovery doesn't find it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = _bracket(user_input[CONF_HOST])
            node_id = await self._async_fetch_node_id(host)
            if node_id is None:
                errors["base"] = "unreachable"
            else:
                await self.async_set_unique_id(node_id, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._host = host
                self._node_id = node_id
                self.context["title_placeholders"] = {"node_id": node_id}
                return await self.async_step_adopt()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def _async_fetch_node_id(self, host: str) -> str | None:
        """Ask an unclaimed node at `host` for its id (GET /info)."""
        session = async_get_clientsession(self.hass)
        url = f"http://{host}:{NODE_ADOPT_PORT}/info"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.info("No unclaimed Noticom node at %s: %r", url, err)
            return None
        node_id = body.get("node_id") if isinstance(body, dict) else None
        return node_id if isinstance(node_id, str) and node_id else None

    async def async_step_adopt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm, then ask the user to press the node's button."""
        errors: dict[str, str] = {}
        default_name = f"Noticom {self._node_id}"
        if user_input is not None:
            name = (user_input.get(CONF_NAME) or "").strip() or default_name
            try:
                node_pubkey = await self._async_adopt()
            except AdoptError as err:
                errors["base"] = err.reason
            else:
                hub = self.hass.data.get(DOMAIN)
                defaults = hub.node_defaults if hub is not None else dict(OPTION_DEFAULTS)
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NODE_ID: self._node_id,
                        CONF_NODE_PUBKEY: node_pubkey,
                    },
                    options=defaults,  # the admin defaults from the panel
                )
            default_name = name
        return self.async_show_form(
            step_id="adopt",
            data_schema=vol.Schema({vol.Optional(CONF_NAME, default=default_name): str}),
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
                    vol.Coerce(int), vol.Range(min=0, max=27)
                ),
                vol.Required(CONF_BUTTON_NC, default=opts[CONF_BUTTON_NC]): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
