"""End to end: the real noticom-node control client against this integration.

Skipped unless the node package is importable (pip install -e ../noticom-node).
"""

import asyncio

import numpy as np
import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.noticom import protocol
from custom_components.noticom.const import CONF_NODE_ID, CONF_NODE_PUBKEY, DOMAIN
from custom_components.noticom.identity import async_get_server_key

control = pytest.importorskip("noticom_node.control")
node_state = pytest.importorskip("noticom_node.state")


class FakeNode:
    """Records configs the node would apply."""

    def __init__(self, button_pin=13, button_nc=False):
        self.configs = []
        self.button = (button_pin, button_nc)
        self.changed = asyncio.Event()

    async def apply(self, config):
        self.configs.append(config)
        self.changed.set()
        restart = (config["button_pin"], config["button_nc"]) != self.button
        return control.ApplyResult(restart=restart)

    async def next_config(self):
        await asyncio.wait_for(self.changed.wait(), 3)
        self.changed.clear()
        return self.configs[-1]


@pytest.fixture
async def setup(hass, hass_client_no_auth, tmp_path):
    """HA with Noticom loaded, an adopted node entry, and the node's state dir."""
    state = node_state.NodeState(tmp_path)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=state.node_id,
        title="Hallway",
        data={
            CONF_NODE_ID: state.node_id,
            CONF_NODE_PUBKEY: protocol.public_key_b64(state.key),
        },
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    server_url = str(client.make_url("")).rstrip("/")
    server_pub = protocol.public_key_b64(await async_get_server_key(hass))
    pairing = node_state.Pairing(server_pub, server_url)
    return entry, state, pairing


async def test_node_connects_and_follows_settings(hass, setup):
    entry, state, pairing = setup
    node = FakeNode()
    task = asyncio.create_task(control.ControlClient(state, pairing, node.apply).run())
    try:
        first = await node.next_config()
        assert first["volume"] == 100 and first["name"] == "Hallway"
        await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.hallway_connected").state == "on"

        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": "number.hallway_volume", "value": 35}, blocking=True,
        )
        assert (await node.next_config())["volume"] == 35
        assert not task.done()
    finally:
        task.cancel()


async def test_button_change_restarts_node(hass, setup):
    entry, state, pairing = setup
    node = FakeNode()
    task = asyncio.create_task(control.ControlClient(state, pairing, node.apply).run())
    await node.next_config()
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "button_pin": 17}
    )
    assert await asyncio.wait_for(task, 3) is control.Outcome.RESTART


async def test_removing_node_unpairs_it(hass, setup):
    entry, state, pairing = setup
    node = FakeNode()
    task = asyncio.create_task(control.ControlClient(state, pairing, node.apply).run())
    await node.next_config()
    await hass.config_entries.async_remove(entry.entry_id)
    assert await asyncio.wait_for(task, 3) is control.Outcome.UNPAIRED


async def test_node_rejects_impostor_server(hass, setup):
    """A server without the adoption key can't configure the node."""
    entry, state, pairing = setup
    wrong = node_state.Pairing(
        protocol.public_key_b64(protocol.generate_private_key()), pairing.server_url
    )
    node = FakeNode()
    task = asyncio.create_task(control.ControlClient(state, wrong, node.apply).run())
    await asyncio.sleep(1.5)
    assert node.configs == []  # welcome refused: server signature didn't verify
    assert not task.done()  # keeps retrying, doesn't give up or reset
    task.cancel()


async def test_chime_syncs_and_plays_on_node(hass, hass_client_no_auth, tmp_path):
    """The whole chime path: folder -> HA -> signed download -> node queue -> speaker."""
    import hashlib

    from noticom_node.chimecache import ChimeCache
    from noticom_node.player import Player

    from .audio_fixtures import write_wav

    hass.config.config_dir = str(tmp_path / "ha")
    folder = tmp_path / "ha" / "noticom" / "chimes"
    folder.mkdir(parents=True)
    write_wav(folder / "mailbox.wav")

    state = node_state.NodeState(tmp_path / "node")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=state.node_id, title="Hallway",
        data={CONF_NODE_ID: state.node_id, CONF_NODE_PUBKEY: protocol.public_key_b64(state.key)},
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    pairing = node_state.Pairing(
        protocol.public_key_b64(await async_get_server_key(hass)),
        str(client.make_url("")).rstrip("/"),
    )

    cache = ChimeCache(tmp_path / "cache")
    played = []
    finished = asyncio.Event()

    async def speaker(path):
        played.append(path.read_bytes())
        finished.set()

    player = Player(cache, speaker)
    playback = asyncio.create_task(player.run())
    node = FakeNode()
    task = asyncio.create_task(
        control.ControlClient(state, pairing, node.apply, player=player, cache=cache).run()
    )
    try:
        await node.next_config()
        chime = hass.data[DOMAIN].chimes.get("mailbox")
        for _ in range(50):  # wait for the background sync
            if cache.path(chime.hash):
                break
            await asyncio.sleep(0.05)
        assert cache.path(chime.hash) is not None

        result = await hass.services.async_call(
            DOMAIN, "play_chime", {"chime": "mailbox"}, blocking=True, return_response=True
        )
        assert result["played"] == ["Hallway"]
        await asyncio.wait_for(finished.wait(), 3)
        assert hashlib.sha256(played[0]).hexdigest() == chime.hash
    finally:
        task.cancel()
        playback.cancel()


async def test_intercom_message_between_two_real_nodes(hass, hass_client_no_auth, tmp_path):
    """Hallway records and sends; Kitchen plays the intercom chime, then the message."""
    import hashlib

    from noticom_node.audio import process_recording
    from noticom_node.chimecache import ChimeCache
    from noticom_node.player import Player

    hass.config.config_dir = str(tmp_path / "ha")
    (tmp_path / "ha" / "noticom" / "chimes").mkdir(parents=True)

    nodes = {}
    for name in ("Hallway", "Kitchen"):
        state = node_state.NodeState(tmp_path / name)
        MockConfigEntry(
            domain=DOMAIN, unique_id=state.node_id, title=name,
            data={CONF_NODE_ID: state.node_id, CONF_NODE_PUBKEY: protocol.public_key_b64(state.key)},
        ).add_to_hass(hass)
        nodes[name] = state
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    pairing = node_state.Pairing(
        protocol.public_key_b64(await async_get_server_key(hass)),
        str(client.make_url("")).rstrip("/"),
    )

    heard: list[bytes] = []
    done = asyncio.Event()

    async def kitchen_speaker(path):
        heard.append(path.read_bytes())
        if len(heard) == 2:
            done.set()

    kitchen_cache = ChimeCache(tmp_path / "kcache")
    kitchen_player = Player(kitchen_cache, kitchen_speaker)
    hall_player = Player(ChimeCache(tmp_path / "hcache"), kitchen_speaker)
    tasks = [asyncio.create_task(kitchen_player.run()), asyncio.create_task(hall_player.run())]
    hall_fake, kit_fake = FakeNode(), FakeNode()
    hall = control.ControlClient(nodes["Hallway"], pairing, hall_fake.apply, player=hall_player)
    kit = control.ControlClient(
        nodes["Kitchen"], pairing, kit_fake.apply, player=kitchen_player, cache=kitchen_cache
    )
    tasks += [asyncio.create_task(hall.run()), asyncio.create_task(kit.run())]
    try:
        await hall_fake.next_config()
        await kit_fake.next_config()

        # What the Hallway node would upload after a 1 s hold (stereo capture -> mono WAV).
        t = np.arange(16000) / 16000
        stereo = np.repeat((0.05 * np.sin(2 * np.pi * 300 * t) * 32767).astype("<i2"), 2)
        message = process_recording(stereo.tobytes())
        assert await hall.upload_clip(message)

        await asyncio.wait_for(done.wait(), 5)
        intercom = hass.data[DOMAIN].chimes.get("intercom")
        assert hashlib.sha256(heard[0]).hexdigest() == intercom.hash  # the chime first
        assert heard[1] == message  # then the message, byte for byte
        await asyncio.sleep(0.1)
        recent = hass.data[DOMAIN].intercom.recent()
        assert recent[0]["sender"] == "Hallway"
        assert recent[0]["recipients"] == [{"name": "Kitchen", "status": "done"}]
    finally:
        for task in tasks:
            task.cancel()
