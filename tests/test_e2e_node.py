"""End to end: the real noticom-node control client against this integration.

Skipped unless the node package is importable (pip install -e ../noticom-node).
"""

import asyncio

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
