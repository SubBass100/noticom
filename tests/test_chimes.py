"""Chime folder scanning, conversion, the file endpoint and actions."""

import hashlib
import io
import time
import wave

import numpy as np
import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component

from custom_components.noticom import protocol
from custom_components.noticom.audio import TARGET_PEAK
from custom_components.noticom.const import DOMAIN

from .audio_fixtures import write_mp3, write_wav
from .conftest import NODE_ID
from .test_websocket import handshake


@pytest.fixture
def chime_dir(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "noticom" / "chimes"
    folder.mkdir(parents=True)
    return folder


async def load(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return hass.data[DOMAIN]


def peak_and_channels(path):
    with wave.open(str(path)) as wav:
        ch = wav.getnchannels()
        data = np.frombuffer(wav.readframes(wav.getnframes()), "<i2") / 32768
    return float(np.abs(data).max()), ch


async def test_wav_and_mp3_are_normalized_to_mono(hass, chime_dir, tmp_path):
    write_wav(chime_dir / "doorbell.wav", amp=0.1)
    if write_mp3(chime_dir / "Mailbox.mp3", tmp_path / "src.wav") is None:
        pytest.skip("ffmpeg not installed")
    (chime_dir / "notes.txt").write_text("ignored")
    hub = await load(hass)

    names = [c.name for c in hub.chimes.chimes]
    assert names == ["doorbell", "Mailbox"]
    for chime in hub.chimes.chimes:
        peak, channels = peak_and_channels(chime.path)
        assert channels == 1
        assert abs(peak - TARGET_PEAK) < 0.02
        assert hashlib.sha256(chime.path.read_bytes()).hexdigest() == chime.hash
    assert hub.chimes.get("mailbox").name == "Mailbox"  # case-insensitive


async def test_broken_file_is_skipped(hass, chime_dir):
    (chime_dir / "broken.mp3").write_bytes(b"not audio")
    write_wav(chime_dir / "entry.wav")
    hub = await load(hass)
    assert [c.name for c in hub.chimes.chimes] == ["entry"]


async def test_reload_picks_up_changes_and_tells_nodes(
    hass, chime_dir, hass_client_no_auth, node_entry, node_key
):
    write_wav(chime_dir / "entry.wav")
    hub = await load(hass)
    client = await hass_client_no_auth()
    ws = await client.ws_connect("/api/noticom/ws")
    welcome, _ = await handshake(ws, node_key)
    assert [c["name"] for c in welcome["chimes"]] == ["entry"]

    write_wav(chime_dir / "exit.wav", amp=0.3)
    (chime_dir / "entry.wav").unlink()
    await hass.services.async_call(DOMAIN, "reload_chimes", blocking=True)
    msg = protocol.decode((await ws.receive(timeout=2)).data)
    assert msg["t"] == "chimes"
    assert [c["name"] for c in msg["chimes"]] == ["exit"]
    # Old cache file pruned.
    assert len(list(hub.chimes.cache.glob("*.wav"))) == 1
    await ws.close()


async def test_chime_download_requires_signature(
    hass, chime_dir, hass_client_no_auth, node_entry, node_key
):
    write_wav(chime_dir / "doorbell.wav")
    hub = await load(hass)
    chime = hub.chimes.get("doorbell")
    client = await hass_client_no_auth()
    path = f"/api/noticom/chime/{chime.hash}"

    assert (await client.get(path)).status == 401
    ts = int(time.time())
    headers = {
        "X-Noticom-Node": NODE_ID,
        "X-Noticom-Time": str(ts),
        "X-Noticom-Sig": protocol.sign(
            node_key, protocol.request_signing_payload("GET", path, ts)
        ),
    }
    resp = await client.get(path, headers=headers)
    assert resp.status == 200
    assert hashlib.sha256(await resp.read()).hexdigest() == chime.hash

    stale = dict(headers, **{"X-Noticom-Time": str(ts - 60)})
    assert (await client.get(path, headers=stale)).status == 401
    bad = dict(headers, **{"X-Noticom-Sig": protocol.sign(
        protocol.generate_private_key(), protocol.request_signing_payload("GET", path, ts))})
    assert (await client.get(path, headers=bad)).status == 401


async def test_play_chime_targets_and_reports(
    hass, chime_dir, hass_client_no_auth, node_entry, node_key
):
    write_wav(chime_dir / "doorbell.wav")
    hub = await load(hass)
    client = await hass_client_no_auth()
    ws = await client.ws_connect("/api/noticom/ws")
    await handshake(ws, node_key)

    result = await hass.services.async_call(
        DOMAIN, "play_chime", {"chime": "Doorbell"}, blocking=True, return_response=True
    )
    assert result == {"chime": "doorbell", "played": ["Hallway"], "offline": []}
    msg = protocol.decode((await ws.receive(timeout=2)).data)
    assert msg["t"] == "play" and msg["kind"] == "chime"
    assert msg["chime_hash"] == hub.chimes.get("doorbell").hash

    # Targeting by the node's entity works too.
    await hass.services.async_call(
        DOMAIN, "play_chime",
        {"chime": "doorbell", "entity_id": "number.hallway_volume"}, blocking=True,
    )
    assert protocol.decode((await ws.receive(timeout=2)).data)["t"] == "play"

    await hass.services.async_call(DOMAIN, "stop", {}, blocking=True)
    assert protocol.decode((await ws.receive(timeout=2)).data)["t"] == "stop"
    await ws.close()


async def test_play_unknown_chime_errors(hass, chime_dir, node_entry):
    write_wav(chime_dir / "doorbell.wav")
    await load(hass)
    with pytest.raises(ServiceValidationError, match="Available: doorbell"):
        await hass.services.async_call(DOMAIN, "play_chime", {"chime": "nope"}, blocking=True)


async def test_play_chime_offline_node(hass, chime_dir, node_entry):
    write_wav(chime_dir / "doorbell.wav")
    await load(hass)
    result = await hass.services.async_call(
        DOMAIN, "play_chime", {"chime": "doorbell"}, blocking=True, return_response=True
    )
    assert result["offline"] == ["Hallway"] and result["played"] == []
