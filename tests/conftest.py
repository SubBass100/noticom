"""Shared fixtures for Noticom integration tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.noticom import protocol
from custom_components.noticom.const import CONF_NODE_ID, CONF_NODE_PUBKEY, DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"

NODE_ID = "c3453904ce42"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


@pytest.fixture
def node_key():
    """The fake node's private key."""
    return protocol.generate_private_key()


@pytest.fixture
def node_entry(hass, node_key):
    """An adopted node's config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=NODE_ID,
        title="Hallway",
        data={CONF_NODE_ID: NODE_ID, CONF_NODE_PUBKEY: protocol.public_key_b64(node_key)},
    )
    entry.add_to_hass(hass)
    return entry
