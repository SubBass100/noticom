"""Node software: newest-version check, update entity, Update all."""

import asyncio

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from custom_components.noticom import protocol
from custom_components.noticom.const import DOMAIN, NODE_VERSION_URL, WS_PATH

from .conftest import NODE_ID

UPDATE = "update.hallway_node_software"


async def connect(client, node_key, version):
    ws = await client.ws_connect(WS_PATH)
    challenge = protocol.decode((await ws.receive()).data)
    await ws.send_str(protocol.encode(
        "auth", node_id=NODE_ID, nonce=protocol.new_nonce(), version=version,
        sig=protocol.sign(node_key, protocol.b64d(challenge["nonce"])),
    ))
    assert protocol.decode((await ws.receive()).data)["t"] == "welcome"
    return ws


async def settle(hass):
    for _ in range(3):
        await asyncio.sleep(0.03)
        await hass.async_block_till_done()


@pytest.mark.check_latest
async def test_latest_version_from_github(hass, aioclient_mock, node_entry):
    aioclient_mock.get(NODE_VERSION_URL, text='[project]\nname = "noticom-node"\nversion = "0.9.1"\n')
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert hass.data[DOMAIN].software.latest == "0.9.1"


@pytest.mark.check_latest
async def test_github_unreachable_keeps_known_version(hass, aioclient_mock, node_entry):
    aioclient_mock.get(NODE_VERSION_URL, exc=TimeoutError())
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert hass.data[DOMAIN].software.latest == "0.3.0"


async def test_update_entity_and_install(hass, hass_client_no_auth, node_entry, node_key):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    hass.data[DOMAIN].software.latest = "0.4.0"
    client = await hass_client_no_auth()
    ws = await connect(client, node_key, "0.3.0")
    await settle(hass)

    state = hass.states.get(UPDATE)
    assert state.state == "on"
    assert state.attributes["installed_version"] == "0.3.0"
    assert state.attributes["latest_version"] == "0.4.0"
    device = dr.async_get(hass).async_get_device({(DOMAIN, NODE_ID)})
    assert device.sw_version == "0.3.0"

    await hass.services.async_call("update", "install", {"entity_id": UPDATE}, blocking=True)
    msg = protocol.decode((await ws.receive(timeout=2)).data)
    assert msg == {"t": "update", "ref": "main"}
    assert hass.states.get(UPDATE).attributes["in_progress"] is True

    # The node restarts on the new version and reconnects.
    await ws.close()
    await settle(hass)
    ws = await connect(client, node_key, "0.4.0")
    await settle(hass)
    state = hass.states.get(UPDATE)
    assert state.state == "off"
    assert state.attributes["in_progress"] is False
    assert dr.async_get(hass).async_get_device({(DOMAIN, NODE_ID)}).sw_version == "0.4.0"
    await ws.close()


async def test_node_ahead_is_not_downgraded(hass, hass_client_no_auth, node_entry, node_key):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    ws = await connect(await hass_client_no_auth(), node_key, "0.5.0")  # newer than known 0.2.0
    await settle(hass)
    state = hass.states.get(UPDATE)
    assert state.state == "off" and state.attributes["latest_version"] == "0.5.0"
    await ws.close()


async def test_update_error_clears_progress(hass, hass_client_no_auth, node_entry, node_key):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    hass.data[DOMAIN].software.latest = "0.4.0"
    ws = await connect(await hass_client_no_auth(), node_key, "0.3.0")
    await settle(hass)
    await hass.services.async_call("update", "install", {"entity_id": UPDATE}, blocking=True)
    await ws.receive(timeout=2)
    await ws.send_str(protocol.encode("state", updating=None, update_error="systemd-run failed"))
    await settle(hass)
    assert hass.states.get(UPDATE).attributes["in_progress"] is False
    await ws.close()


async def test_offline_node_cannot_update(hass, node_entry):
    from homeassistant.exceptions import HomeAssistantError

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    hass.data[DOMAIN].software.latest = "0.4.0"
    with pytest.raises(HomeAssistantError, match="offline"):
        await hass.services.async_call("update", "install", {"entity_id": UPDATE}, blocking=True)


async def test_panel_update_all(hass, hass_client_no_auth, hass_ws_client, node_entry, node_key):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    hass.data[DOMAIN].software.latest = "0.4.0"
    node = await connect(await hass_client_no_auth(), node_key, "0.3.0")
    await settle(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/nodes/update"})
    res = (await ws.receive_json())["result"]
    assert res["started"] == ["Hallway"] and res["skipped"] == []
    assert res["software"]["nodes"][0]["updating"] is True
    assert protocol.decode((await node.receive(timeout=2)).data)["t"] == "update"
    # Already updating: a second Update all doesn't resend.
    await ws.send_json({"id": 2, "type": "noticom/nodes/update"})
    assert (await ws.receive_json())["result"]["started"] == []
    await node.close()


async def test_old_node_needs_one_ssh_update(hass, hass_client_no_auth, hass_ws_client, node_entry, node_key):
    """0.2.0 nodes can't update themselves: HA says so instead of waiting forever."""
    from homeassistant.exceptions import HomeAssistantError

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    node = await connect(await hass_client_no_auth(), node_key, "0.2.0")
    await settle(hass)
    assert hass.states.get(UPDATE).state == "on"  # 0.3.0 is newer
    with pytest.raises(HomeAssistantError, match="over SSH"):
        await hass.services.async_call("update", "install", {"entity_id": UPDATE}, blocking=True)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/nodes/update"})
    res = (await ws.receive_json())["result"]
    assert res["started"] == [] and res["skipped"] == ["Hallway"]
    assert res["software"]["nodes"][0]["remote_update"] is False
    await node.close()
