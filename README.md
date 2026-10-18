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

> **Status: early.** Adoption, the live node connection, per-node settings,
> chimes and the Noticom sidebar panel (chime upload, preview and delete)
> work. The push-to-talk intercom is next.

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
   services as a discovered device; click **Adopt** and press the node's
   button within 60 seconds.

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

Play one from any automation with **Noticom: Play chime**. Target nodes by
device, entity or area, or leave the target empty for every node:

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

## Development

```sh
pip install -r requirements_test.txt
pip install -e ../noticom-node   # optional: enables the end-to-end tests
python -m pytest
```

## License

Apache-2.0
