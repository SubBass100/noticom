"""Adopting nodes: by discovery and by IP address."""

import ipaddress

import pytest
from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.noticom import protocol
from custom_components.noticom.const import DOMAIN

from .conftest import NODE_ID

HOST = "10.0.4.169"


@pytest.fixture(autouse=True)
def internal_url(hass):
    hass.config.internal_url = "http://10.0.4.69:8123"


def fake_node(aioclient_mock, node_key, host=HOST, node_id=NODE_ID, press=True):
    """Mock a node's adoption server: /info and a correctly signed /adopt."""
    aioclient_mock.get(f"http://{host}:8742/info", json={"node_id": node_id, "version": "0.1.0"})

    async def adopt(method, url, data):
        if not press:
            return AiohttpClientMockResponse(method, url, status=408)
        assert data["server_url"] == "http://10.0.4.69:8123"
        return AiohttpClientMockResponse(method, url, json={
            "node_id": node_id,
            "node_pubkey": protocol.public_key_b64(node_key),
            "sig": protocol.sign(node_key, protocol.b64d(data["nonce"])),
        })

    aioclient_mock.post(f"http://{host}:8742/adopt", side_effect=adopt)


async def test_add_by_ip(hass, aioclient_mock, node_key):
    fake_node(aioclient_mock, node_key)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": f" {HOST} "})
    assert result["step_id"] == "adopt"
    assert result["description_placeholders"] == {"node_id": NODE_ID}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Kitchen"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Kitchen"
    assert result["data"]["node_id"] == NODE_ID
    assert result["data"]["node_pubkey"] == protocol.public_key_b64(node_key)
    assert result["result"].unique_id == NODE_ID


async def test_add_by_ip_unreachable(hass, aioclient_mock):
    aioclient_mock.get(f"http://{HOST}:8742/info", exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["errors"] == {"base": "unreachable"}


async def test_add_by_ip_already_adopted(hass, aioclient_mock, node_entry, node_key):
    fake_node(aioclient_mock, node_key)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] == "abort" and result["reason"] == "already_configured"


async def test_button_not_pressed(hass, aioclient_mock, node_key):
    fake_node(aioclient_mock, node_key, press=False)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "button_timeout"}


async def test_forged_reply_rejected(hass, aioclient_mock, node_key):
    """A device that can't sign with the key it claims is refused."""
    aioclient_mock.get(f"http://{HOST}:8742/info", json={"node_id": NODE_ID})

    async def adopt(method, url, data):
        return AiohttpClientMockResponse(method, url, json={
            "node_id": NODE_ID,
            "node_pubkey": protocol.public_key_b64(node_key),
            "sig": protocol.sign(protocol.generate_private_key(), protocol.b64d(data["nonce"])),
        })

    aioclient_mock.post(f"http://{HOST}:8742/adopt", side_effect=adopt)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "invalid_reply"}


async def test_discovery_prefers_ipv4(hass, aioclient_mock, node_key):
    fake_node(aioclient_mock, node_key)
    info = ZeroconfServiceInfo(
        ip_address=ipaddress.ip_address("fe80::1"),
        ip_addresses=[ipaddress.ip_address("fe80::1"), ipaddress.ip_address(HOST)],
        port=8742, hostname="noticom-hallway.local.", type="_noticom._tcp.local.",
        name=f"noticom-{NODE_ID}._noticom._tcp.local.",
        properties={"node_id": NODE_ID, "version": "0.1.0"},
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info)
    assert result["step_id"] == "adopt"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"


async def test_new_node_gets_admin_defaults(hass, aioclient_mock, node_key, tmp_path):
    from homeassistant.setup import async_setup_component

    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, DOMAIN, {})
    hub = hass.data[DOMAIN]
    hub.settings["node_defaults"] = {"volume": 60, "button_pin": 17, "intercom_targets": []}
    fake_node(aioclient_mock, node_key)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    entry = result["result"]
    assert entry.title == f"Noticom {NODE_ID}"  # default name when left as-is
    assert entry.options["volume"] == 60
    assert entry.options["button_pin"] == 17
    assert entry.options["intercom_targets"] == []
    assert entry.options["mic_gain"] == 90  # untouched defaults filled in
