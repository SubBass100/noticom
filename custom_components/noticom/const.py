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

# Storage.
STORAGE_VERSION = 1
STORAGE_KEY = "noticom"
CHIME_DIR = "noticom/chimes"  # relative to the HA config dir

# Behaviour.
MAX_CLIP_SECONDS = 45
CLIP_TTL_S = 600
ADOPT_TIMEOUT_S = 75  # node waits 60 s for a button press; allow for latency

# Admin defaults.
DEFAULT_BUTTON_PIN = 17  # ReSpeaker 2-Mic HAT onboard button
DEFAULT_CHIME_PRIORITY = True
DEFAULT_VOLUME = 70

# Actions.
SERVICE_PLAY_CHIME = "play_chime"
SERVICE_BROADCAST = "broadcast"
SERVICE_STOP = "stop"
