"""The node control channel, driven by a scripted fake node."""

import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.noticom import protocol
from custom_components.noticom.const import DOMAIN, WS_PATH
from custom_components.noticom.identity import async_get_server_key

from .conftest import NODE_ID

SENSOR = "binary_sensor.hallway_connected"
VOLUME = "number.hallway_volume"


async def setup(hass: HomeAssistant, entry) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def handshake(ws, node_key, node_id=NODE_ID):
    """Do the node's half of the handshake; return (reply, node_nonce)."""
    challenge = protocol.decode((await ws.receive()).data)
    assert challenge["t"] == "challenge"
    node_nonce = protocol.new_nonce()
    await ws.send_str(
        protocol.encode(
            "auth",
            node_id=node_id,
            nonce=node_nonce,
            version="0.1.0",
            sig=protocol.sign(node_key, protocol.b64d(challenge["nonce"])),
        )
    )
    return protocol.decode((await ws.receive()).data), node_nonce


async def test_auth_welcome_and_connectivity(hass, hass_client_no_auth, node_entry, node_key):
    await setup(hass, node_entry)
    assert hass.states.get(SENSOR).state == "off"
    server_pub = protocol.public_key_b64(await async_get_server_key(hass))

    client = await hass_client_no_auth()
    ws = await client.ws_connect(WS_PATH)
    welcome, node_nonce = await handshake(ws, node_key)
    assert welcome["t"] == "welcome"
    # Mutual auth: the server proved it holds the key the node saved.
    assert protocol.verify(server_pub, protocol.b64d(node_nonce), welcome["sig"])
    assert welcome["config"]["name"] == "Hallway"
    assert welcome["config"]["volume"] == 100
    assert welcome["config"]["button_pin"] == 13
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "on"

    await ws.close()
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "off"


async def test_bad_signature_rejected(hass, hass_client_no_auth, node_entry):
    await setup(hass, node_entry)
    client = await hass_client_no_auth()
    ws = await client.ws_connect(WS_PATH)
    reply, _ = await handshake(ws, protocol.generate_private_key())  # wrong key
    assert reply == {"t": "error", "reason": "bad_signature"}
    assert hass.states.get(SENSOR).state == "off"


async def test_unknown_node_told_to_unpair(hass, hass_client_no_auth, node_entry, node_key):
    await setup(hass, node_entry)
    server_pub = protocol.public_key_b64(await async_get_server_key(hass))
    client = await hass_client_no_auth()
    ws = await client.ws_connect(WS_PATH)
    reply, node_nonce = await handshake(ws, node_key, node_id="deadbeef0000")
    assert reply["t"] == "unpair"
    assert protocol.verify(server_pub, protocol.unpair_payload(node_nonce), reply["sig"])


async def test_setting_change_pushes_config(hass, hass_client_no_auth, node_entry, node_key):
    await setup(hass, node_entry)
    client = await hass_client_no_auth()
    ws = await client.ws_connect(WS_PATH)
    await handshake(ws, node_key)

    await hass.services.async_call(
        "number", "set_value", {"entity_id": VOLUME, "value": 40}, blocking=True
    )
    msg = protocol.decode((await ws.receive(timeout=2)).data)
    assert msg["t"] == "config"
    assert msg["config"]["volume"] == 40
    assert hass.states.get(VOLUME).state == "40"
    await ws.close()


async def test_node_state_is_recorded(hass, hass_client_no_auth, node_entry, node_key):
    await setup(hass, node_entry)
    client = await hass_client_no_auth()
    ws = await client.ws_connect(WS_PATH)
    await handshake(ws, node_key)
    await ws.send_str(protocol.encode("state", queue_depth=0, playing=False))
    await asyncio.sleep(0.05)
    assert hass.data[DOMAIN].links[NODE_ID].state == {"queue_depth": 0, "playing": False}
    await ws.close()


async def test_removing_node_sends_unpair(hass, hass_client_no_auth, node_entry, node_key):
    await setup(hass, node_entry)
    server_pub = protocol.public_key_b64(await async_get_server_key(hass))
    client = await hass_client_no_auth()
    ws = await client.ws_connect(WS_PATH)
    _, node_nonce = await handshake(ws, node_key)

    await hass.config_entries.async_remove(node_entry.entry_id)
    msg = protocol.decode((await ws.receive(timeout=2)).data)
    assert msg["t"] == "unpair"
    assert protocol.verify(server_pub, protocol.unpair_payload(node_nonce), msg["sig"])


async def test_options_flow_sets_button(hass, node_entry):
    await setup(hass, node_entry)
    result = await hass.config_entries.options.async_init(node_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"button_pin": 17, "button_nc": True}
    )
    assert result["type"] == "create_entry"
    assert node_entry.options["button_pin"] == 17
    assert node_entry.options["button_nc"] is True


async def test_node_mid_adoption_is_not_unpaired(hass, hass_client_no_auth, node_key):
    """A node that connects before its entry exists must not be wiped."""
    assert await async_setup_component(hass, DOMAIN, {})
    # Simulate an unfinished adoption flow for this node.
    hass.config_entries.flow.async_progress_by_handler = lambda handler: [
        {"context": {"unique_id": "newnode00001"}}
    ]
    client = await hass_client_no_auth()
    ws = await client.ws_connect(WS_PATH)
    reply, _ = await handshake(ws, node_key, node_id="newnode00001")
    assert reply == {"t": "error", "reason": "not_ready"}
