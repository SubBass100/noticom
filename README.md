# Noticom

Notification chimes and push-to-talk intercom for Home Assistant, using
Raspberry Pi nodes with a ReSpeaker 2-Mic HAT, a small speaker and a button.

- Play chimes (WAV/MP3) on chosen nodes from any automation, e.g. a doorbell
  playing "dingdong" everywhere.
- Hold a node's button to record a message (up to 45 s); release to send it to
  the nodes it's allowed to reach, announced by a chime.
- Adopt nodes from the HA UI with a physical button-press confirmation; each
  node is bonded to your HA with an Ed25519 keypair.

> **Status: early.** Discovery, adoption and the live node connection work:
> each node shows up with Connected, Volume, Mic gain, Mic boost and Push to
> talk entities, and its button wiring is under Configure. Chimes, the
> panel and the intercom itself are next.

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

## Development

```sh
pip install -r requirements_test.txt
pip install -e ../noticom-node   # optional: enables the end-to-end tests
python -m pytest
```

## License

Apache-2.0
