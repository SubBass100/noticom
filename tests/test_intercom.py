"""Intercom: clip upload, routing, delivery, event, and the panel's view of it."""

import asyncio
import time

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.noticom import protocol
from custom_components.noticom.const import CONF_NODE_ID, CONF_NODE_PUBKEY, DOMAIN

from .audio_fixtures import write_wav
from .conftest import NODE_ID
from .test_websocket import handshake

KITCHEN = "kitchen00001"


def signed(key, node_id, method, path):
    ts = int(time.time())
    return {
        "X-Noticom-Node": node_id,
        "X-Noticom-Time": str(ts),
        "X-Noticom-Sig": protocol.sign(key, protocol.request_signing_payload(method, path, ts)),
    }


@pytest.fixture
async def two_nodes(hass, tmp_path, node_entry, node_key, hass_client_no_auth):
    """Hallway (node_entry) and Kitchen, both connected."""
    hass.config.config_dir = str(tmp_path)
    kitchen_key = protocol.generate_private_key()
    kitchen = MockConfigEntry(
        domain=DOMAIN, unique_id=KITCHEN, title="Kitchen",
        data={CONF_NODE_ID: KITCHEN, CONF_NODE_PUBKEY: protocol.public_key_b64(kitchen_key)},
    )
    kitchen.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    hall_ws = await client.ws_connect("/api/noticom/ws")
    await handshake(hall_ws, node_key)
    kit_ws = await client.ws_connect("/api/noticom/ws")
    await handshake(kit_ws, kitchen_key, node_id=KITCHEN)
    clip = write_wav(tmp_path / "msg.wav", seconds=1.0, rate=16000, channels=1).read_bytes()
    return {
        "client": client, "hall_ws": hall_ws, "kit_ws": kit_ws, "hall_key": node_key,
        "kitchen_key": kitchen_key, "hallway": node_entry, "kitchen": kitchen, "clip": clip,
    }


async def upload(n, key=None, node_id=NODE_ID, body=None):
    return await n["client"].post(
        "/api/noticom/clip", data=body if body is not None else n["clip"],
        headers={**signed(key or n["hall_key"], node_id, "POST", "/api/noticom/clip"),
                 "Content-Type": "audio/wav"},
    )


async def test_message_reaches_other_nodes_not_sender(hass, two_nodes):
    n = two_nodes
    events = async_capture_events(hass, "noticom_message")
    resp = await upload(n)
    assert resp.status == 200, await resp.text()
    clip_id = (await resp.json())["clip_id"]

    play = protocol.decode((await n["kit_ws"].receive(timeout=2)).data)
    assert play["t"] == "play" and play["kind"] == "clip"
    assert play["clip_url"] == f"/api/noticom/clip/{clip_id}"
    intercom_hash = hass.data[DOMAIN].chimes.get("intercom").hash
    assert play["pre_chime_hash"] == intercom_hash

    # Kitchen fetches the clip with its own signature and gets the same audio.
    got = await n["client"].get(
        play["clip_url"], headers=signed(n["kitchen_key"], KITCHEN, "GET", play["clip_url"])
    )
    assert got.status == 200 and await got.read() == n["clip"]
    # The sender wasn't a recipient, so it can't fetch it.
    nope = await n["client"].get(
        play["clip_url"], headers=signed(n["hall_key"], NODE_ID, "GET", play["clip_url"])
    )
    assert nope.status == 404

    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["sender"] == "Hallway"
    assert events[0].data["recipients"] == ["Kitchen"]
    assert events[0].data["duration"] == 1.0

    # Delivery progress shows up in recent messages.
    await n["kit_ws"].send_str(protocol.encode("job", job_id=play["job_id"], status="done"))
    await asyncio.sleep(0.05)
    recent = hass.data[DOMAIN].intercom.recent()
    assert recent[0]["sender"] == "Hallway"
    assert recent[0]["recipients"] == [{"name": "Kitchen", "status": "done"}]


async def test_routing_limits_recipients(hass, two_nodes):
    n = two_nodes
    hass.config_entries.async_update_entry(n["hallway"], options={"intercom_targets": []})
    await hass.async_block_till_done()
    # The option change pushes a config to Hallway; drain it.
    protocol.decode((await n["hall_ws"].receive(timeout=2)).data)
    resp = await upload(n)
    assert (await resp.json())["recipients"] == 0
    assert hass.data[DOMAIN].intercom.recent()[0]["recipients"] == []


async def test_ptt_disabled_refuses_upload(hass, two_nodes):
    n = two_nodes
    hass.config_entries.async_update_entry(n["hallway"], options={"ptt_enabled": False})
    await hass.async_block_till_done()
    assert (await upload(n)).status == 403


async def test_bad_uploads(hass, two_nodes):
    n = two_nodes
    assert (await upload(n, body=b"not a wav")).status == 400
    assert (await upload(n, key=protocol.generate_private_key())).status == 401


async def test_panel_intercom_api(hass, two_nodes, hass_ws_client, hass_client):
    n = two_nodes
    clip_id = (await (await upload(n)).json())["clip_id"]
    ws = await hass_ws_client(hass)

    await ws.send_json({"id": 1, "type": "noticom/intercom/get"})
    state = (await ws.receive_json())["result"]
    assert state["chime"] == "intercom"
    assert [x["name"] for x in state["nodes"]] == ["Hallway", "Kitchen"]
    assert all(x["connected"] and x["targets"] == "all" for x in state["nodes"])
    assert state["messages"][0]["id"] == clip_id

    await ws.send_json({"id": 2, "type": "noticom/intercom/set_targets",
                        "node_id": NODE_ID, "targets": [KITCHEN, NODE_ID, "bogus"]})
    state = (await ws.receive_json())["result"]
    assert next(x for x in state["nodes"] if x["name"] == "Hallway")["targets"] == [KITCHEN]

    await ws.send_json({"id": 3, "type": "noticom/intercom/set_chime", "chime": None})
    assert (await ws.receive_json())["result"]["chime"] is None
    await ws.send_json({"id": 4, "type": "noticom/intercom/set_chime", "chime": "nope"})
    assert (await ws.receive_json())["error"]["code"] == "not_found"

    # With no intercom chime, plays carry no pre-chime.
    await upload(n)
    kit = n["kit_ws"]
    msgs = []
    while True:
        m = protocol.decode((await kit.receive(timeout=2)).data)
        if m["t"] == "play":
            msgs.append(m)
            if len(msgs) == 2:
                break
    assert msgs[1]["pre_chime_hash"] is None

    admin = await hass_client()
    resp = await admin.get(f"/api/noticom/panel/clip/{clip_id}")
    assert resp.status == 200 and await resp.read() == n["clip"]
