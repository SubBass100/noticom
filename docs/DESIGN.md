# Noticom design

Noticom is a notification-chime and push-to-talk intercom system for Home
Assistant. It has two parts:

| Part | Repo | Runs on |
|---|---|---|
| Server (custom integration, domain `noticom`) | [`noticom`](https://github.com/SubBass100/noticom) | Home Assistant (developed against HA OS) |
| Node software (`noticom-node`) | [`noticom-node`](https://github.com/SubBass100/noticom-node) | Raspberry Pi 3+ with a ReSpeaker 2-Mic Pi HAT, a small speaker and a button |

This file is the source of truth for decisions and the wire protocol. Both
repos are built against it; change it here first.

## Decisions

- **Integration only, no add-on.** Everything (discovery, adoption, WebSocket
  endpoint, chime storage, routing, sidebar panel) runs inside the `noticom`
  custom integration, installed via HACS.
- **Nodes connect out to HA** over a persistent, authenticated WebSocket. HA
  never needs node IPs after adoption; online/offline status comes for free.
- **Store-and-forward intercom.** Hold the button to record (max 45 s),
  release to send. No live streaming, no reply feature. Presses shorter than
  ~0.5 s are discarded as accidental taps.
- **Chimes are pre-cached on nodes**, matched by SHA-256 hash, so a doorbell
  only needs a tiny "play" message. Uploaded MP3s are normalized to WAV on the
  server so nodes never decode MP3.
- **Queue on the node:** one item playing plus up to 5 waiting. A 6th arriving
  item is dropped and reported as `dropped`.
- **Chime priority** is an admin option, **on by default**: a chime is
  inserted after any waiting chimes but ahead of waiting clips. It never
  interrupts the item currently playing.
- **Offline nodes are not queued for.** A job targeting an offline node is
  dropped server-side; a doorbell from ten minutes ago is not useful.
- **Network/hostname changes apply with rollback:** if the node cannot
  reconnect to HA within 60 s, it reverts and reports failure.
- **Mono audio.** Output is mixed to mono in the codec (the speaker sits on
  one channel). Recordings capture both mics in stereo, are averaged to mono
  (~3 dB less hiss), DC-offset removed and peak-normalized to about -1 dBFS
  (gain capped at +26 dB) before upload. Chimes get the same normalization
  when uploaded to HA.
- **Licence:** Apache-2.0 for both repos.

## Home Assistant surface

Each adopted node is an HA device with:

| Entity | Purpose |
|---|---|
| `media_player` | Lets TTS and `media_player.play_media` target the node |
| `number` (volume, mic gain) | Audio levels |
| `switch` (PTT enabled) | Disable the intercom button |
| `binary_sensor` (connected) | Online status |

Actions:

- `noticom.play_chime` — `chime` name, targets devices/areas (or all nodes).
- `noticom.broadcast` — play an arbitrary audio file on target nodes.
- `noticom.stop` — stop playback and clear queues on target nodes.

Per-node settings editable from HA: name, hostname, DHCP or static IP, audio
output device, volume, mic gain and boost, button GPIO pin (admin-set default,
GPIO17 = the HAT's onboard button) or PTT disabled, and the allow-list of nodes
(or all) its intercom messages go to.

The sidebar panel manages chimes (upload WAV/MP3, preview, delete), the
intercom announce chime, routing, and admin defaults (default button pin,
chime priority).

## Protocol

### 1. Discovery and adoption (node unclaimed)

The unclaimed node runs a local HTTP server on **port 8742** and advertises
`_noticom._tcp.local.` with TXT records `node_id`, `version`.

1. HA discovers the service and shows a discovery card; the user clicks
   **Adopt**.
2. HA sends `POST http://<node>:8742/adopt` with
   `{"server_pubkey": "<b64 ed25519>", "nonce": "<b64 32 bytes>", "server_url": "http://<ha>:8123"}`.
3. The node chirps and waits up to **60 s for a button press** (physical
   presence check). No press → `408`.
4. On press the node replies
   `{"node_id": "...", "node_pubkey": "<b64>", "sig": "<b64 sign(raw nonce bytes)>"}`,
   stores the server key and URL, stops the adoption server and stops
   advertising as unclaimed.
5. HA verifies `sig` and creates the device. The node trusts only that server
   key until factory reset (hold the button ~10 s while the service starts).

### 2. Control channel (adopted)

The node opens `ws(s)://<ha>:8123/api/noticom/ws`. This endpoint does its own
Ed25519 auth, not HA user tokens. All frames are JSON objects with a `t`
(type) field.

Handshake:

```
server → node  {"t":"challenge","nonce":"<b64>"}
node → server  {"t":"auth","node_id":"...","sig":"<b64 sign(raw nonce bytes)>","version":"..."}
server → node  {"t":"welcome","config":{...},"chimes":[{"name":"dingdong","hash":"<sha256 hex>","size":12345}]}
```

Server → node:

| `t` | Payload |
|---|---|
| `config` | Full node config (see below) |
| `chimes` | Chime manifest; node downloads missing hashes, deletes unlisted ones |
| `play` | `job_id`, `kind` (`chime`/`clip`), `chime_hash`, `clip_url`, `pre_chime_hash`, `priority` |
| `stop` | Stop current job and clear the queue |
| `ping` | Keepalive |

Node → server:

| `t` | Payload |
|---|---|
| `state` | `volume`, `queue_depth`, `playing` |
| `ptt` | `phase`: `start` or `sent` (with `clip_id`) |
| `job` | `job_id`, `status`: `started`/`done`/`dropped`/`error` |
| `config_result` | `ok` (bool), `reason` |
| `pong` | Keepalive reply |

Node config object:

```json
{
  "name": "Kitchen",
  "hostname": "noticom-kitchen",
  "network": {"mode": "dhcp"},
  "output_device": "default",
  "volume": 100,
  "mic_gain": 90,
  "mic_boost": 3,
  "button_pin": 17,
  "ptt_enabled": true,
  "chime_priority": true
}
```

`network` may instead be
`{"mode": "static", "address": "192.168.1.50/24", "gateway": "192.168.1.1", "dns": ["192.168.1.1"]}`.

### 3. File transfer (HTTP)

| Method | Path | Use |
|---|---|---|
| `GET` | `/api/noticom/chime/{hash}` | Node downloads a chime (WAV) |
| `POST` | `/api/noticom/clip` | Node uploads a PTT recording (16 kHz mono 16-bit WAV) → `{"clip_id": "..."}` |
| `GET` | `/api/noticom/clip/{id}` | Node fetches a clip it was told to play |

Every request carries:

```
X-Noticom-Node: <node_id>
X-Noticom-Time: <unix seconds>
X-Noticom-Sig:  <b64 sign("<METHOD>\n<path>\n<time>")>
```

Requests older than 30 s are rejected. A clip is deleted once every target
node reports `done`/`dropped`/`error`, or after a 10-minute TTL.

### 4. Behaviour rules

- **PTT:** press → beep → record; release or 45 s cap → stop and upload; send
  `ptt` `sent`. The server fans out `play {kind: "clip", pre_chime_hash: <intercom chime>}`
  to every node on the sender's allow-list except the sender.
- **Queue:** 1 playing + 5 waiting; 6th → `dropped`. With `chime_priority`,
  chimes go after waiting chimes, before waiting clips; never interrupt.
- **Offline targets:** not queued server-side.

## Hardware notes (ReSpeaker 2-Mic HAT)

Tested on a Pi 3, Raspberry Pi OS based on Debian 13 (trixie), kernel
6.18.50+rpt-rpi-v8, Keyestudio ReSpeaker 2-Mic HAT.

- The board has no HAT ID EEPROM. The codec is identified over I2C bus 1:
  **0x1a = WM8960 (v1 / Keyestudio)**, 0x18 = TLV320AIC3104 (v2, not yet
  supported).
- **Use the stock overlay:** `dtoverlay=wm8960-soundcard,alsaname=seeed2micvoicec`.
  Seeed's `respeaker-2mic-v1_0` overlay loads and shows the card, but never
  supplies the 12.288 MHz MCLK: playback fails with `Input/output error` and
  dmesg shows `bcm2835-i2s ... FIFO clear timed out: no PCM clock`.
- Always address the HAT as `plughw:CARD=seeed2micvoicec,DEV=0`; card 0 is
  the Pi's headphone jack.
- The WM8960 powers up with output mixers and mic inputs disconnected. The
  node applies this mixer state at startup (`noticom_node/mixer.py`):

| Control | Value | Notes |
|---|---|---|
| Left/Right Output Mixer PCM | on | DAC to outputs |
| DAC Mono Mix | Mono | Same audio on both channels |
| PCM Playback -6dB | off | |
| Playback | 100% | DAC digital, 100% = 0 dB |
| Speaker AC / Speaker DC | 5 | Class-D boost 1.8x; drop to 3-4 if it distorts or the Pi browns out |
| **Speaker** | **100%** | **HA volume** |
| Left/Right Boost Mixer LINPUT1/RINPUT1 | on | The two mics |
| Left/Right Input Mixer Boost | on | |
| **Left/Right Input Boost Mixer LINPUT1/RINPUT1** | **3** | **HA mic boost** (0-3 = 0/13/20/29 dB) |
| **Capture** | **90% cap** | **HA mic gain** |
