"""Constants for the Noticom integration."""

from __future__ import annotations

DOMAIN = "noticom"

# mDNS service type advertised by unclaimed nodes.
ZEROCONF_TYPE = "_noticom._tcp.local."

# Port the node's adoption server listens on while unclaimed.
NODE_ADOPT_PORT = 8742

# HTTP / WebSocket endpoints served by this integration.
WS_PATH = "/api/noticom/ws"
CHIME_PATH = "/api/noticom/chime/{chime_hash}"
CLIP_UPLOAD_PATH = "/api/noticom/clip"
CLIP_PATH = "/api/noticom/clip/{clip_id}"

# Request-signing headers (see docs/DESIGN.md §3).
HDR_NODE = "X-Noticom-Node"
HDR_TIME = "X-Noticom-Time"
HDR_SIG = "X-Noticom-Sig"
MAX_REQUEST_AGE_S = 30

# Config entry data keys.
CONF_NODE_ID = "node_id"
CONF_NODE_PUBKEY = "node_pubkey"

# Config entry option keys (per-node settings).
CONF_VOLUME = "volume"
CONF_MIC_GAIN = "mic_gain"
CONF_MIC_BOOST = "mic_boost"
CONF_PTT_ENABLED = "ptt_enabled"
CONF_BUTTON_PIN = "button_pin"
CONF_BUTTON_NC = "button_nc"
CONF_INTERCOM_TARGETS = "intercom_targets"  # "all" or a list of node ids
CONF_OUTPUT_DEVICE = "output_device"  # "auto" or an ALSA card id reported by the node

# Config entry data: what the node's hardware can do (reported on connect).
CONF_CAPS = "caps"

# Storage.
STORAGE_VERSION = 1
STORAGE_KEY = "noticom"
CHIME_DIR = "noticom/chimes"  # relative to the HA config dir
CHIME_CACHE_DIR = "noticom/.cache"  # normalized copies, named by hash
CHIME_SCAN_INTERVAL_S = 30

# Behaviour.
MAX_CLIP_SECONDS = 45
CLIP_TTL_S = 3600  # recent messages kept in memory (last 10) for up to an hour
ADOPT_TIMEOUT_S = 75  # node waits 60 s for a button press; allow for latency

# Admin defaults.
DEFAULT_BUTTON_PIN = 13  # Grove connector; 17 is the HAT's onboard button
DEFAULT_BUTTON_NC = False  # normally open
DEFAULT_CHIME_PRIORITY = True
DEFAULT_VOLUME = 100
DEFAULT_MIC_GAIN = 90
DEFAULT_MIC_BOOST = 3
DEFAULT_PTT_ENABLED = True
DEFAULT_INTERCOM_CHIME = "intercom"

# Events.
EVENT_MESSAGE = "noticom_message"

PLATFORMS = ["binary_sensor", "number", "switch"]

# Actions.
SERVICE_PLAY_CHIME = "play_chime"
SERVICE_BROADCAST = "broadcast"
SERVICE_STOP = "stop"
SERVICE_RELOAD_CHIMES = "reload_chimes"
ATTR_CHIME = "chime"
