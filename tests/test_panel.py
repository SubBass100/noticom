"""The sidebar panel's API: list, upload, preview, delete."""

import aiohttp
import pytest
from homeassistant.setup import async_setup_component

from custom_components.noticom.const import DOMAIN

from .audio_fixtures import write_wav

UPLOAD = "/api/noticom/panel/chimes"


@pytest.fixture
async def panel(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "noticom" / "chimes"
    folder.mkdir(parents=True)
    write_wav(folder / "doorbell.wav")
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return folder


def form(name, data, filename="clip.wav", replace=False):
    f = aiohttp.FormData()
    f.add_field("name", name)
    f.add_field("replace", "true" if replace else "false")
    f.add_field("file", data, filename=filename, content_type="audio/wav")
    return f


async def test_panel_registered(hass, panel):
    panels = hass.data["frontend_panels"]
    assert panels["noticom"].sidebar_title == "Noticom"
    assert panels["noticom"].require_admin


async def test_list_chimes(hass, panel, hass_ws_client):
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/chimes/list"})
    res = await ws.receive_json()
    assert res["success"]
    assert [c["name"] for c in res["result"]["chimes"]] == ["doorbell", "intercom"]
    assert res["result"]["chimes"][0]["file"] == "doorbell.wav"
    assert res["result"]["chimes"][0]["duration"] == pytest.approx(0.2, abs=0.01)


async def test_upload_preview_replace_delete(hass, panel, hass_client, hass_ws_client, tmp_path):
    client = await hass_client()
    data = write_wav(tmp_path / "src.wav").read_bytes()

    resp = await client.post(UPLOAD, data=form("Front door", data))
    body = await resp.json()
    assert resp.status == 200, body
    assert body["chime"] == "Front door"
    assert (panel / "Front door.wav").exists()
    assert not list(panel.glob(".upload-*"))
    chime = next(c for c in body["chimes"] if c["name"] == "Front door")

    preview = await client.get(f"/api/noticom/panel/chime/{chime['hash']}")
    assert preview.status == 200 and (await preview.read())[:4] == b"RIFF"

    # Same name again: refused unless replacing.
    resp = await client.post(UPLOAD, data=form("front door", data))
    assert resp.status == 400
    assert "already exists" in (await resp.json())["error"]
    louder = write_wav(tmp_path / "loud.wav", seconds=0.5).read_bytes()
    resp = await client.post(UPLOAD, data=form("Front door", louder, replace=True))
    assert resp.status == 200
    assert hass.data[DOMAIN].chimes.get("front door").duration == pytest.approx(0.5, abs=0.01)

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/chimes/delete", "name": "Front door"})
    res = await ws.receive_json()
    assert res["success"]
    assert [c["name"] for c in res["result"]["chimes"]] == ["doorbell", "intercom"]
    assert not (panel / "Front door.wav").exists()


@pytest.mark.parametrize(
    ("name", "data", "filename", "error"),
    [
        ("../evil", b"RIFF", "x.wav", "Chime names can use"),
        ("ok", b"RIFF", "x.ogg", "WAV or MP3"),
        ("ok", b"definitely not audio", "x.mp3", "couldn't be read"),
    ],
)
async def test_upload_rejects_bad_input(hass, panel, hass_client, name, data, filename, error):
    client = await hass_client()
    resp = await client.post(UPLOAD, data=form(name, data, filename=filename))
    assert resp.status == 400
    assert error in (await resp.json())["error"]
    assert sorted(p.name for p in panel.iterdir()) == ["doorbell.wav", "intercom.wav"]


async def test_non_admin_is_refused(
    hass, panel, hass_client, hass_ws_client, hass_read_only_access_token, tmp_path
):
    client = await hass_client(hass_read_only_access_token)
    data = write_wav(tmp_path / "src.wav").read_bytes()
    assert (await client.post(UPLOAD, data=form("sneaky", data))).status == 403
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    await ws.send_json({"id": 1, "type": "noticom/chimes/delete", "name": "doorbell"})
    res = await ws.receive_json()
    assert not res["success"] and res["error"]["code"] == "unauthorized"
    assert (panel / "doorbell.wav").exists()


async def test_delete_unknown(hass, panel, hass_ws_client):
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/chimes/delete", "name": "nope"})
    res = await ws.receive_json()
    assert not res["success"] and res["error"]["code"] == "not_found"
