<p align="center">
  <img src="custom_components/noticom/brand/icon@2x.png" alt="Noticom icon" width="140">
</p>

<h1 align="center">Noticom</h1>

<p align="center"><b>Chimes and a push-to-talk intercom for Home Assistant, using cheap Raspberry Pi speakers around your home.</b></p>

---

## What it does

- 🔔 **Plays sounds when things happen.** Mail arrives, someone rings the
  doorbell, a door opens: pick a sound and pick which rooms hear it.
- 🎃 **Themes for holidays.** Spooky sounds all October, a harp on
  Valentine's Day, and your normal sounds the rest of the year. They switch
  automatically.
- 🎙️ **Works as an intercom.** Hold the button on any speaker, talk, let go.
  Your message plays in the other rooms.
- 🖥️ **Everything is managed in Home Assistant.** Upload sounds, choose who
  can talk to whom, and change volume, all from one page.

Each speaker is a small box we call a **node**: a Raspberry Pi with
something to play sound on, and usually a button. You can have as many as
you like, and mix and match:

- **ReSpeaker HAT** or **USB sound card with a mic**: chimes **and** intercom
- **The Pi's headphone jack** with powered speakers: chimes only

## What you need

- **Home Assistant** (version 2026.3 or newer) with [HACS](https://hacs.xyz)
  installed.
- **One or more nodes.** Each one needs:
  - a Raspberry Pi 3 or newer
  - a ReSpeaker 2-Mic Pi HAT (the Keyestudio version works too) with a
    small speaker, **or** a USB sound card, **or** powered speakers on the
    headphone jack
  - a push button, if you want to use it as an intercom

Building a node is covered in the
[noticom-node instructions](https://github.com/SubBass100/noticom-node).

## Setup

### 1. Install Noticom in Home Assistant

1. Open **HACS**, click the **⋮** menu (top right) and choose **Custom
   repositories**.
2. Paste `https://github.com/SubBass100/noticom`, choose type
   **Integration**, and click **Add**.
3. Search HACS for **Noticom** and click **Download**.
4. Restart Home Assistant (**Settings → System → ⋮ → Restart**).

A **Noticom** page now appears in the sidebar.

### 2. Set defaults for your speakers (optional)

Open **Noticom → Settings** and choose the starting volume, button
settings and so on. Every node you add from now on starts with these.

### 3. Add your nodes

Set up a node using the
[noticom-node instructions](https://github.com/SubBass100/noticom-node). The
install command is also in **Noticom → Settings → Add a node**, with a
**Copy** button. Then in Home Assistant:

1. Go to **Settings → Devices & services**. The node shows up under
   **Discovered** within a minute or two.
2. Click **Add**, give it a name (usually the room, like *Kitchen*), and
   click **Submit**.
3. The node beeps. **Press its button within 60 seconds** to confirm. No
   button? Run `sudo noticom-node pair` on the Pi instead.

That's it. The node is connected.

> **Node not showing up?** Click **Add integration**, search for
> **Noticom**, and type in the node's IP address instead.

### 4. Add some sounds

Open **Noticom → Sounds**, drag in a WAV or MP3 file, give it a name like
*mailbox*, and click **Upload**. Leave **Also make a chime** ticked, and
it's ready to use in automations. You can preview it in your browser or
play it on all your nodes to test.

## Chimes, sounds and themes

Three words to know:

- A **sound** is an audio file you uploaded, like *classic-dingdong* or
  *spooky-doorbell*.
- A **chime** is the name your automations use, like *doorbell*,
  *mailbox* or *garbage*.
- A **theme** decides which sound each chime makes.

Your automations always say "play *doorbell*" and never need changing. The
theme decides whether that's *classic-dingdong* or *spooky-doorbell*.

| Chime | Default | Halloween | Valentine's Day |
|---|---|---|---|
| doorbell | classic-dingdong | spooky-doorbell | cupid-harp |
| mailbox | soft-ping | creaky-gate | *(uses Default)* |
| intercom | ding-ding | ghost-whoosh | *(uses Default)* |

**Default** is the catch-all: it plays whenever no other theme is on, and it
fills in any chime a theme leaves blank. So a holiday theme only needs the
chimes you want to change.

Everything is on the **Noticom → Themes** tab:

- **The table** has a row per chime and a column per theme. Pick a sound
  in each box. Under each chime you can see which automations use it
  (click one to open it).
- **Add a chime** at the bottom of the table, say *garbage* for a new bin
  sensor. Pick its Default sound and you're done. Holiday themes play the
  Default sound until you pick something else for them.
- **Add a theme**, then click **Edit** to give it dates, like *Oct 1 – Oct
  31* or *Feb 14*. Dates repeat every year and can cross New Year (*Dec 20 –
  Jan 2*). You can also limit them to certain hours, like *5 PM – 11 PM*.
- **When themes overlap**, the shorter date range wins, so a one-day
  *Birthday* theme beats an all-month *Halloween*. If two ranges are the
  same length, the theme higher in the list wins (use the arrows to
  reorder).
- **To switch by hand**, pick a theme in the **Theme** box at the top (or
  use the `select.noticom_theme` entity in automations and dashboards).
  Choose **Automatic** to follow the schedule again.
  `sensor.noticom_active_theme` shows which theme is playing.

The panel also warns you about problems, like a chime with no Default
sound, or an automation that plays a chime that doesn't exist (a typo, say).

On the **Sounds** tab you can filter sounds by theme, or show the ones
that aren't used anywhere. Use **Themes** on a sound to file it under a
theme, which lists it first when picking sounds for that theme. A sound
can be used in as many chimes and themes as you like. Deleting a sound
that's in use tells you where first; holiday themes then go back to their
Default sound.

## Playing a sound from an automation

1. In your automation, click **+ Add action**, search for **Noticom**, and
   choose **Play chime**.
2. Pick the **Chime** from the list.
3. Click **+ Choose device** (or area) to pick which nodes play it. **Leave
   it empty to play on every node.**

The current theme picks the sound. Here's the same thing in YAML, playing
the *mailbox* chime in two rooms:

```yaml
actions:
  - action: noticom.play_chime
    target:
      area_id: [kitchen, office]
    data:
      chime: mailbox
```

To play in rooms like this, assign each node to an area: **Settings →
Devices & services → Noticom**, pick the node, and click the pencil.

To play one exact sound and ignore themes, use `sound: spooky-doorbell`
instead of `chime:`.

**Noticom: Stop** silences nodes right away.

## Using the intercom

1. **Hold** the button on a node.
2. Wait for the short **beep**, then talk (up to 45 seconds).
3. **Let go** to send.

The other nodes play a short chime, then your message. A quick tap does
nothing, so a bumped button won't send anything. A low tone means the
message couldn't be sent, usually because the node is offline.

In **Noticom → Intercom** you can:

- choose the sound that plays before messages (themes can change it too:
  it's the *intercom* chime)
- choose **who each node can talk to**: all nodes, or only some
- **listen to recent messages** and see which rooms heard them

Automations can react to messages too. Every message fires a
`noticom_message` event:

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

## Settings for each node

Each node appears as a device in Home Assistant with:

| Setting | What it does |
|---|---|
| **Connected** | Shows if the node is online |
| **Volume** | Speaker volume |
| **Mic gain** / **Mic boost** | How sensitive the microphone is. Turn these down if messages sound distorted |
| **Push to talk** | Turn the intercom button on or off |
| **Sound output** | Which speaker to use if the node has more than one (ReSpeaker, USB, headphone jack, HDMI). *Automatic* picks the best one |

Chime-only nodes (no microphone or no button) don't have the mic and push
to talk settings, and show as **Chime only** on the Intercom tab. They
still play chimes and other nodes' intercom messages.

The **button wiring** (which pin, and normally open or normally closed) is
under the node's **Configure** button. Pin 0 means no button.

## Updating nodes

Each node has a **Node software** update in Home Assistant. When a new
version of the node software is out, it shows up under **Settings →
Updates** like any other update: click **Install** and the node updates
itself and restarts (a few minutes on a Pi 3). **Noticom → Settings → Node
software** lists every node's version, with an **Update all** button.

Nodes on version 0.2.0 or older need one update over SSH first (run the
install command on them again); after that they can update from Home
Assistant.

## Removing or resetting a node

- **Delete it in Home Assistant**, and the node resets itself, ready to be
  added again.
- **Or reset it from the button:** press it **5 times quickly**. The node
  asks you to **hold the button for 5 seconds** to confirm. If you let go
  early or don't press, nothing happens.
- **Or from the Pi:** run `sudo noticom-node reset`.

## Troubleshooting

| Problem | What to try |
|---|---|
| Node doesn't appear under Discovered | Use **Add integration → Noticom** and type its IP address |
| "Couldn't reach the node" when adding | Update the node (re-run its install line). As a quick workaround, run `ping -c 3 <Home Assistant IP>` on the Pi and try again. If you reflashed the Pi, ignore old Noticom cards and add it by IP |
| No sound from a node | Check its **Volume**, and that the speaker is plugged into the HAT's speaker port |
| Messages are too quiet or too loud | Adjust that node's **Mic gain** and **Mic boost** |
| Something else | Check **Settings → System → Logs** and search for `noticom` |

## For developers

- How it all works (protocol, security, audio): [docs/DESIGN.md](docs/DESIGN.md)
- Run the tests:
  ```sh
  pip install -r requirements_test.txt
  pip install -e ../noticom-node   # optional: also runs the end-to-end tests
  python -m pytest
  ```

## License

[Apache-2.0](LICENSE)
