"""Settings tab API: chime priority and defaults for new nodes."""

from homeassistant.setup import async_setup_component

from custom_components.noticom import protocol
from custom_components.noticom.const import DOMAIN

from .test_websocket import handshake

DEFAULTS = {
    "volume": 70, "mic_gain": 80, "mic_boost": 2, "ptt_enabled": False,
    "button_pin": 17, "button_nc": True, "intercom_targets": [],
}


async def test_settings_roundtrip_and_priority_push(
    hass, tmp_path, hass_ws_client, hass_client_no_auth, node_entry, node_key
):
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    node = await (await hass_client_no_auth()).ws_connect("/api/noticom/ws")
    welcome, _ = await handshake(node, node_key)
    assert welcome["config"]["chime_priority"] is True

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/settings/get"})
    state = (await ws.receive_json())["result"]
    assert state["chime_priority"] is True
    assert state["node_defaults"]["button_pin"] == 13
    assert state["node_defaults"]["intercom_targets"] == "all"

    await ws.send_json({"id": 2, "type": "noticom/settings/set",
                        "chime_priority": False, "node_defaults": DEFAULTS})
    res = await ws.receive_json()
    assert res["success"], res
    assert res["result"]["chime_priority"] is False
    assert res["result"]["node_defaults"] == DEFAULTS
    # The priority change is pushed to connected nodes straight away.
    msg = protocol.decode((await node.receive(timeout=2)).data)
    assert msg["t"] == "config" and msg["config"]["chime_priority"] is False
    # Saved for next time.
    assert hass.data[DOMAIN].node_defaults["volume"] == 70


async def test_settings_validation(hass, tmp_path, hass_ws_client):
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, DOMAIN, {})
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/settings/set",
                        "node_defaults": {**DEFAULTS, "button_pin": 40}})
    res = await ws.receive_json()
    assert not res["success"] and res["error"]["code"] == "invalid_format"


async def test_settings_include_install_commands_and_versions(
    hass, tmp_path, hass_ws_client, hass_client_no_auth, node_entry, node_key
):
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/settings/get"})
    state = (await ws.receive_json())["result"]
    assert state["commands"]["install"].startswith("curl -sSL https://raw.githubusercontent.com/SubBass100/noticom-node/main/install.sh")
    assert "NOTICOM_BUTTON_PIN=none" in state["commands"]["install_no_button"]
    assert state["commands"]["pair"] == "sudo noticom-node pair"
    node = state["software"]["nodes"][0]
    assert node["name"] == "Hallway" and node["version"] is None and not node["connected"]
