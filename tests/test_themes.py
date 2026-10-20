"""Chimes, themes, the schedule, and finding automations that use chimes."""

from datetime import datetime

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component

from custom_components.noticom import protocol
from custom_components.noticom.const import DOMAIN
from custom_components.noticom.themes import ThemeError, range_days, range_matches

from .audio_fixtures import write_wav
from .test_websocket import handshake


@pytest.fixture
def sounds(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "noticom" / "chimes"
    folder.mkdir(parents=True)
    for name in ("doorbell", "mailbox", "spooky", "cupid", "cake"):
        write_wav(folder / f"{name}.wav", amp=0.1 + len(name) / 100)
    return folder


async def load(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return hass.data[DOMAIN]


def at(month, day, hour=12, minute=0):
    return datetime(2026, month, day, hour, minute)


async def test_existing_sounds_become_default_chimes(hass, sounds):
    hub = await load(hass)
    themes = hub.themes
    assert themes.chime_names() == ["cake", "cupid", "doorbell", "intercom", "mailbox", "spooky"]
    assert themes.resolve("Doorbell")[0] == "doorbell"
    assert themes.resolve("intercom")[0] == "intercom"
    assert themes.problems() == []


async def test_intercom_setting_carries_over(hass, sounds, hass_storage):
    hass_storage["noticom.settings"] = {
        "version": 1, "key": "noticom.settings",
        "data": {"default_chime_created": True, "intercom_chime": "mailbox"},
    }
    hub = await load(hass)
    assert hub.themes.resolve("intercom")[0] == "mailbox"
    assert hub.intercom.chime_name == "mailbox"


def test_ranges():
    october = {"start": "10-01", "end": "10-31", "from": None, "to": None}
    winter = {"start": "12-20", "end": "01-02", "from": None, "to": None}
    evening = {"start": "10-01", "end": "10-31", "from": "17:00", "to": "23:00"}
    late = {"start": "12-31", "end": "12-31", "from": "22:00", "to": "02:00"}
    assert range_days(october) == 31
    assert range_days(winter) == 14
    assert range_matches(october, at(10, 15)) and not range_matches(october, at(11, 1))
    assert range_matches(winter, at(12, 25)) and range_matches(winter, at(1, 2))
    assert not range_matches(winter, at(1, 3))
    assert range_matches(evening, at(10, 15, 18)) and not range_matches(evening, at(10, 15, 16))
    assert not range_matches(evening, at(10, 15, 23))  # end time is exclusive
    assert range_matches(late, at(12, 31, 23, 30)) and not range_matches(late, at(12, 31, 21))


async def test_schedule_shortest_wins_then_priority(hass, sounds):
    themes = (await load(hass)).themes
    halloween = await themes.async_add_theme("Halloween")
    birthday = await themes.async_add_theme("Birthday")
    party = await themes.async_add_theme("Party")
    await themes.async_update_theme(halloween["id"], schedule=[{"start": "10-01", "end": "10-31"}])
    await themes.async_update_theme(birthday["id"], schedule=[{"start": "10-12", "end": "10-12"}])
    await themes.async_update_theme(party["id"], schedule=[{"start": "10-12", "end": "10-12"}])

    assert themes.active(at(10, 5))[0]["name"] == "Halloween"
    assert themes.active(at(10, 5))[1] == "schedule"
    # Oct 12: Birthday and Party are both 1 day; Birthday is higher in the list.
    assert themes.active(at(10, 12))[0]["name"] == "Birthday"
    await themes.async_reorder([party["id"], birthday["id"], halloween["id"]])
    assert themes.active(at(10, 12))[0]["name"] == "Party"
    assert themes.active(at(11, 1))[0]["name"] == "Default"

    # The year view shows who wins each day.
    runs = {(r["start"], r["end"]): r["theme_id"] for r in themes.calendar()}
    assert runs[("10-01", "10-11")] == halloween["id"]
    assert runs[("10-12", "10-12")] == party["id"]
    assert runs[("10-13", "10-31")] == halloween["id"]

    # Manual mode beats the schedule until set back to automatic.
    await themes.async_set_mode(birthday["id"])
    assert themes.active(at(3, 1))[:2] == (birthday, "manual")
    await themes.async_set_mode("auto")
    assert themes.active(at(3, 1))[0]["name"] == "Default"


async def test_theme_falls_back_to_default(hass, sounds):
    themes = (await load(hass)).themes
    halloween = await themes.async_add_theme("Halloween")
    await themes.async_update_theme(halloween["id"], schedule=[{"start": "10-01", "end": "10-31"}])
    await themes.async_set_sound(halloween["id"], "doorbell", "spooky")

    assert themes.resolve("doorbell", at(10, 20)) == ("spooky", halloween)
    assert themes.resolve("mailbox", at(10, 20))[0] == "mailbox"  # not set: Default's
    assert themes.resolve("doorbell", at(12, 1))[0] == "doorbell"

    # Clearing a holiday theme's pick means "use Default" again.
    await themes.async_set_sound(halloween["id"], "doorbell", None)
    assert themes.resolve("doorbell", at(10, 20))[0] == "doorbell"


async def test_play_chime_uses_active_theme(hass, sounds, hass_client_no_auth, node_entry, node_key):
    hub = await load(hass)
    themes = hub.themes
    halloween = await themes.async_add_theme("Halloween")
    await themes.async_set_sound(halloween["id"], "doorbell", "spooky")
    await themes.async_set_mode(halloween["id"])

    client = await hass_client_no_auth()
    ws = await client.ws_connect("/api/noticom/ws")
    await handshake(ws, node_key)

    result = await hass.services.async_call(
        DOMAIN, "play_chime", {"chime": "doorbell"}, blocking=True, return_response=True
    )
    assert (result["chime"], result["sound"], result["theme"]) == ("doorbell", "spooky", "Halloween")
    msg = protocol.decode((await ws.receive(timeout=2)).data)
    assert msg["chime_hash"] == hub.chimes.get("spooky").hash

    # `sound` plays that exact sound, ignoring themes.
    result = await hass.services.async_call(
        DOMAIN, "play_chime", {"sound": "doorbell"}, blocking=True, return_response=True
    )
    assert (result["chime"], result["sound"], result["theme"]) == (None, "doorbell", None)
    msg = protocol.decode((await ws.receive(timeout=2)).data)
    assert msg["chime_hash"] == hub.chimes.get("doorbell").hash
    await ws.close()


async def test_play_chime_errors(hass, sounds, node_entry):
    themes = (await load(hass)).themes
    await themes.async_add_chime("garbage")  # no sound yet
    assert themes.problems() == ["garbage"]
    with pytest.raises(ServiceValidationError, match="has no sound"):
        await hass.services.async_call(DOMAIN, "play_chime", {"chime": "garbage"}, blocking=True)
    with pytest.raises(ServiceValidationError, match="No chime named 'nope'"):
        await hass.services.async_call(DOMAIN, "play_chime", {"chime": "nope"}, blocking=True)
    with pytest.raises(Exception):  # neither chime nor sound
        await hass.services.async_call(DOMAIN, "play_chime", {}, blocking=True)


async def test_deleting_a_sound_falls_back_and_warns(hass, sounds, hass_ws_client):
    themes = (await load(hass)).themes
    halloween = await themes.async_add_theme("Halloween")
    await themes.async_set_sound(halloween["id"], "doorbell", "spooky")
    await themes.async_set_sound(halloween["id"], "mailbox", "spooky")
    await themes.async_tag_sound("cake", [halloween["id"]])
    assert themes.sound_themes("cake") == ["default", halloween["id"]]

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/sounds/delete", "name": "spooky"})
    res = await ws.receive_json()
    assert res["success"]
    assert {u["chime"] for u in res["result"]["was_used"]} == {"doorbell", "mailbox", "spooky"}
    await themes.async_set_mode(halloween["id"])
    assert themes.resolve("doorbell")[0] == "doorbell"  # Default again
    # It was Default's sound for the "spooky" chime, so that chime now warns.
    assert themes.problems() == ["spooky"]


async def test_chime_and_theme_rules(hass, sounds):
    themes = (await load(hass)).themes
    with pytest.raises(ThemeError, match="built in"):
        await themes.async_delete_chime("intercom")
    with pytest.raises(ThemeError, match="already a chime"):
        await themes.async_add_chime("Doorbell")
    with pytest.raises(ThemeError, match="can't be deleted"):
        await themes.async_delete_theme("default")
    with pytest.raises(ThemeError, match="whenever no other theme"):
        await themes.async_update_theme("default", schedule=[{"start": "01-01", "end": "01-01"}])
    theme = await themes.async_add_theme("Valentine's Day")
    with pytest.raises(ThemeError, match="isn't a real date"):
        await themes.async_update_theme(theme["id"], schedule=[{"start": "02-30", "end": "02-30"}])
    with pytest.raises(ThemeError, match="both a start and an end time"):
        await themes.async_update_theme(
            theme["id"], schedule=[{"start": "02-14", "end": "02-14", "from": "17:00"}]
        )
    with pytest.raises(ThemeError, match="already a theme"):
        await themes.async_add_theme("valentine's day")

    await themes.async_delete_chime("mailbox")
    assert "mailbox" not in themes.chime_names()
    await themes.async_set_mode(theme["id"])
    await themes.async_delete_theme(theme["id"])
    assert themes.mode == "auto"


async def test_entities_follow_themes(hass, sounds):
    themes = (await load(hass)).themes
    halloween = await themes.async_add_theme("Halloween")
    await hass.async_block_till_done()

    select = hass.states.get("select.noticom_theme")
    assert select.state == "Automatic"
    assert select.attributes["options"] == ["Automatic", "Default", "Halloween"]
    assert hass.states.get("sensor.noticom_active_theme").state == "Default"

    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.noticom_theme", "option": "Halloween"}, blocking=True,
    )
    await hass.async_block_till_done()
    assert themes.mode == halloween["id"]
    sensor = hass.states.get("sensor.noticom_active_theme")
    assert sensor.state == "Halloween" and sensor.attributes["reason"] == "manual"


async def test_finds_automations_that_play_chimes(hass, sounds, hass_ws_client):
    await load(hass)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "id": "front_door",
                    "alias": "Front door",
                    "triggers": [{"trigger": "event", "event_type": "ding"}],
                    "actions": [{"action": "noticom.play_chime", "data": {"chime": "doorbell"}}],
                },
                {
                    "id": "mixed",
                    "alias": "Mixed bag",
                    "triggers": [{"trigger": "event", "event_type": "x"}],
                    "actions": [
                        {
                            "choose": [
                                {
                                    "conditions": [],
                                    "sequence": [
                                        {"service": "noticom.play_chime", "data": {"chime": "garbag"}},
                                        {"action": "noticom.play_chime",
                                         "data": {"chime": "{{ states('input_text.c') }}"}},
                                    ],
                                }
                            ]
                        }
                    ],
                },
            ]
        },
    )
    await hass.async_block_till_done()

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "noticom/themes/get"})
    res = (await ws.receive_json())["result"]
    doorbell = next(c for c in res["chimes"] if c["name"] == "doorbell")
    assert [u["name"] for u in doorbell["used_by"]] == ["Front door"]
    assert doorbell["used_by"][0]["edit"] == "/config/automation/edit/front_door"
    assert [(u["name"], u["chime"]) for u in res["unknown"]] == [("Mixed bag", "garbag")]
    assert [u["name"] for u in res["dynamic"]] == ["Mixed bag"]
    intercom = next(c for c in res["chimes"] if c["name"] == "intercom")
    assert intercom["builtin"] and intercom["used_by"][0]["kind"] == "builtin"
    assert res["active"]["name"] == "Default"
