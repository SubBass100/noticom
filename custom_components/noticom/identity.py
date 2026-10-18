"""The server's Ed25519 identity, persisted in HA storage."""

from __future__ import annotations

import asyncio

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from . import protocol
from .const import DOMAIN, STORAGE_VERSION

_IDENTITY_KEY = f"{DOMAIN}.identity"
_LOCK_KEY = f"{DOMAIN}_identity_lock"
_CACHE_KEY = f"{DOMAIN}_identity"


async def async_get_server_key(hass: HomeAssistant) -> Ed25519PrivateKey:
    """Return the server private key, creating and saving it on first use.

    Safe to call from config flows, which may run before async_setup.
    """
    if (cached := hass.data.get(_CACHE_KEY)) is not None:
        return cached
    lock: asyncio.Lock = hass.data.setdefault(_LOCK_KEY, asyncio.Lock())
    async with lock:
        if (cached := hass.data.get(_CACHE_KEY)) is not None:
            return cached
        store: Store[dict[str, str]] = Store(
            hass, STORAGE_VERSION, _IDENTITY_KEY, private=True
        )
        data = await store.async_load()
        if data and "private_key" in data:
            key = protocol.private_key_from_b64(data["private_key"])
        else:
            key = protocol.generate_private_key()
            await store.async_save(
                {"private_key": protocol.private_key_to_b64(key)}
            )
        hass.data[_CACHE_KEY] = key
        return key
