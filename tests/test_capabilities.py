"""Nodes report their hardware; HA shows only the controls they support."""

import asyncio

from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.noticom import protocol
from custom_components.noticom.const import DOMAIN, WS_PATH

from .conftest import NODE_ID

JACK_ONLY = {
    "mic": False, "mic_boost": False, "button": False, "output": "Headphones", "input": None,
    "outputs": [{"id": "Headphones", "label": "Headphone jack", "kind": "jack"},
                {"id": "vc4hdmi", "label": "HDMI (vc4-hdmi)", "kind": "hdmi"}],
}
RESPEAKER = {
    "mic": True, "mic_boost": True, "button": True, "output": "seeed2micvoicec",
    "input": "seeed2micvoicec",
    "outputs": [{"id": "seeed2micvoicec", "label": "ReSpeaker HAT", "kind": "respeaker"}],
}


async def connect(hass, client, node_key, caps):
    ws = await client.ws_connect(WS_PATH)
    challenge = protocol.decode((await ws.receive()).data)
    await ws.send_str(protocol.encode(
        "auth", node_id=NODE_ID, nonce=protocol.new_nonce(), version="0.2.0", caps=caps,
        sig=protocol.sign(node_key, protocol.b64d(challenge["nonce"])),
    ))
    welcome = protocol.decode((await ws.receive()).data)
    assert welcome["t"] == "welcome"
    return ws, welcome


async def settle(hass):
    for _ in range(3):
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()


async def test_old_nodes_keep_all_entities(hass, node_entry):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    for entity_id in ("number.hallway_mic_gain", "number.hallway_mic_boost",
                      "switch.hallway_push_to_talk", "select.hallway_sound_output"):
        assert hass.states.get(entity_id) is not None, entity_id


async def test_chime_only_node_drops_mic_entities(hass, hass_client_no_auth, node_entry, node_key):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    ws, welcome = await connect(hass, await hass_client_no_auth(), node_key, JACK_ONLY)
    assert welcome["config"]["output_device"] == "auto"
    await settle(hass)

    registry = er.async_get(hass)
    assert hass.states.get("number.hallway_volume") is not None
    for entity_id in ("number.hallway_mic_gain", "number.hallway_mic_boost",
                      "switch.hallway_push_to_talk"):
        assert hass.states.get(entity_id) is None, entity_id
        assert registry.async_get(entity_id) is None, entity_id

    output = hass.states.get("select.hallway_sound_output")
    assert output.attributes["options"] == ["Automatic", "Headphone jack", "HDMI (vc4-hdmi)"]
    assert output.state == "Automatic"
    assert output.attributes["playing_on"] == "Headphone jack"

    # Picking an output sends it to the node.
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.hallway_sound_output", "option": "HDMI (vc4-hdmi)"}, blocking=True,
    )
    while (msg := protocol.decode((await ws.receive(timeout=2)).data))["t"] != "config":
        pass
    assert msg["config"]["output_device"] == "vc4hdmi"
    assert hass.states.get("select.hallway_sound_output").state == "HDMI (vc4-hdmi)"
    await ws.close()


async def test_adding_a_mic_brings_entities_back(hass, hass_client_no_auth, node_entry, node_key):
    hass.config_entries.async_update_entry(node_entry, data={**node_entry.data, "caps": JACK_ONLY})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert hass.states.get("number.hallway_mic_gain") is None
    ws, _ = await connect(hass, await hass_client_no_auth(), node_key, RESPEAKER)
    await settle(hass)
    assert hass.states.get("number.hallway_mic_gain") is not None
    assert hass.states.get("switch.hallway_push_to_talk") is not None
    await ws.close()


async def test_panel_marks_chime_only_nodes(hass, hass_client_no_auth, hass_ws_client, node_entry, node_key):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    node, _ = await connect(hass, await hass_client_no_auth(), node_key, JACK_ONLY)
    await settle(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/intercom/get"})
    nodes = (await ws.receive_json())["result"]["nodes"]
    assert nodes[0]["can_talk"] is False
    await node.close()


async def test_no_button_option(hass, node_entry):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(node_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"button_pin": 0, "button_nc": False}
    )
    assert result["type"] == "create_entry"
    assert node_entry.options["button_pin"] == 0
