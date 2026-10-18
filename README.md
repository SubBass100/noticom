# Noticom

Notification chimes and push-to-talk intercom for Home Assistant, using
Raspberry Pi nodes with a ReSpeaker 2-Mic HAT, a small speaker and a button.

- Play named notification chimes (WAV/MP3) on chosen nodes from any
  automation: a mailbox chime in the kitchen, a doorbell everywhere, entry
  and exit chimes by the door.
- Hold a node's button to record a message (up to 45 s); release to send it to
  the nodes it's allowed to reach, announced by a chime.
- Adopt nodes from the HA UI with a physical button-press confirmation; each
  node is bonded to your HA with an Ed25519 keypair.

> **Status: early, feature-complete.** Adoption, the live node connection,
> per-node settings, chimes, the push-to-talk intercom and the Noticom
> sidebar panel all work.

## Repos

- **noticom** (this repo): the Home Assistant custom integration.
- **[noticom-node](https://github.com/SubBass100/noticom-node)**: the Pi node
  software and one-line installer.

Design decisions and the wire protocol live in [docs/DESIGN.md](docs/DESIGN.md).

## Installation (HACS)

1. HACS → ⋮ → Custom repositories → add `https://github.com/SubBass100/noticom`
   as an **Integration**.
2. Install **Noticom** and restart Home Assistant.
3. Install `noticom-node` on a Pi. It appears under Settings → Devices &
   services as a discovered device; click **Add**, then **Submit**, and press
   the node's button within 60 seconds. If it doesn't appear, use **Add
   integration → Noticom** and enter the Pi's IP address instead.

## Chimes

Open **Noticom** in the sidebar (admins only) to upload WAV or MP3 chimes,
name them, preview them in your browser, test them on your nodes, and delete
them. Each chime is normalized to a consistent loudness and copied to every
node ahead of time, so it plays instantly.

Behind the scenes chimes live in **`/config/noticom/chimes/`**, and files
you put there yourself (File editor, Samba) show up too: the file name
without its extension is the chime's name, so `mailbox.mp3` is the chime
`mailbox`. Changes are picked up within 30 seconds, or straight away with
**Noticom: Reload chimes**.

Play one from any automation: **+ Add action → Noticom → Play chime**.
Pick the **Chime** from the dropdown (it lists your current chimes), and
choose nodes with **+ Choose device / area** — or add no targets to play on
every node. In YAML:

```yaml
# Mail's here: chime in the kitchen and office.
actions:
  - action: noticom.play_chime
    target:
      area_id: [kitchen, office]
    data:
      chime: mailbox
```

```yaml
# Front door opened: entry chime everywhere.
actions:
  - action: noticom.play_chime
    data:
      chime: entry
```

Each node plays one thing at a time with up to 5 waiting; chimes go ahead
of waiting intercom messages. Offline nodes are skipped (the action's
response lists which). **Noticom: Stop** stops playback and clears the queue.

## Settings and new nodes

The panel's **Settings** tab holds:

- **Chimes jump the queue** (on by default): a chime plays ahead of
  intercom messages that are still waiting, never cutting off what's
  already playing.
- **Defaults for new nodes**: volume, mic gain and boost, push to talk,
  button pin and type, and whether a new node can talk to all nodes or
  nobody yet. Set these before adopting a batch of Pis.

When adopting, give each node a name (usually its room) in the adoption
form.

## Intercom

Hold a node's button: after a short chirp, talk (up to 45 seconds), then
let go. The message plays on every node that node is allowed to talk to,
after the intercom chime. Quick taps don't record anything, and a low tone
means the message couldn't be sent.

In the **Noticom** panel's **Intercom** tab you choose the intercom chime
(a default `intercom` chime is created on first start; pick any chime or
none), set who each node can talk to (all nodes, or only selected ones),
and play back the last 10 messages from the past hour with their delivery
status. Each node's **Push to talk** switch turns its button off.

Every message fires a `noticom_message` event (`sender`, `sender_device_id`,
`recipients`, `offline`, `duration`), so automations can react:

```yaml
triggers:
  - trigger: event
    event_type: noticom_message
    event_data:
      sender: Garage
actions:
  - action: light.turn_on
    target:
      entity_id: light.kitchen
```

## Development

```sh
pip install -r requirements_test.txt
pip install -e ../noticom-node   # optional: enables the end-to-end tests
python -m pytest
```

## License

Apache-2.0
