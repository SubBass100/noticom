"""Push-to-talk intercom: receive a node's recording and fan it out.

Clips are kept in memory: the last MAX_CLIPS for up to CLIP_TTL_S, which
covers delivery to nodes and the panel's recent-messages list.
"""

from __future__ import annotations

import io
import logging
import uuid
import wave
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import protocol
from .audio import encode_wav
from .const import (
    CLIP_PATH,
    CLIP_TTL_S,
    CONF_INTERCOM_TARGETS,
    CONF_NODE_ID,
    DEFAULT_INTERCOM_CHIME,
    DOMAIN,
    EVENT_MESSAGE,
    MAX_CLIP_SECONDS,
    STORAGE_VERSION,
)

if TYPE_CHECKING:
    from .hub import NoticomHub

_LOGGER = logging.getLogger(__name__)

MAX_CLIPS = 10
MAX_CLIP_BYTES = 3 * 1024 * 1024  # 45 s of 16 kHz mono 16-bit is ~1.4 MB
TARGETS_ALL = "all"


class ClipError(Exception):
    """An uploaded clip was rejected."""


@dataclass
class Clip:
    """One intercom message."""

    id: str
    sender_id: str
    sender_name: str
    created: datetime
    duration: float
    data: bytes
    deliveries: dict[str, dict[str, str]] = field(default_factory=dict)
    # node_id -> {"name": ..., "status": "sent"|"started"|"done"|"dropped"|"error"|"offline"}

    def summary(self) -> dict[str, Any]:
        """As shown in the panel."""
        return {
            "id": self.id,
            "sender": self.sender_name,
            "created": self.created.isoformat(),
            "duration": self.duration,
            "recipients": [
                {"name": d["name"], "status": d["status"]} for d in self.deliveries.values()
            ],
        }


def wav_duration(data: bytes) -> float:
    """Validate a PCM WAV and return its length in seconds."""
    try:
        with wave.open(io.BytesIO(data)) as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
            if wav.getsampwidth() != 2 or wav.getnchannels() not in (1, 2) or rate <= 0:
                raise ClipError("expected 16-bit mono or stereo WAV")
    except (wave.Error, EOFError) as err:
        raise ClipError("not a WAV file") from err
    return frames / rate


def default_intercom_chime() -> bytes:
    """A gentle rising two-note 'ding-ding' used as the default intercom chime."""
    rate = 44100
    out = []
    for freq in (784.0, 1046.5):  # G5 then C6
        t = np.arange(int(rate * 0.32)) / rate
        tone = (
            np.sin(2 * np.pi * freq * t)
            + 0.35 * np.sin(2 * np.pi * 2 * freq * t)
            + 0.12 * np.sin(2 * np.pi * 3 * freq * t)
        )
        envelope = np.minimum(1.0, t / 0.008) * np.exp(-t * 7)
        out.append(tone * envelope)
    samples = np.concatenate(out)
    samples = samples / np.abs(samples).max() * 0.89
    return encode_wav(samples.astype(np.float32), rate)


class Intercom:
    """Receives recordings, routes them, and keeps recent messages."""

    def __init__(self, hass: HomeAssistant, hub: NoticomHub) -> None:
        self.hass = hass
        self.hub = hub
        self.clips: OrderedDict[str, Clip] = OrderedDict()
        self._jobs: dict[str, tuple[str, str]] = {}  # job_id -> (clip_id, node_id)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.settings")
        self.settings: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load settings, and create the default intercom chime the first time."""
        self.settings = await self._store.async_load() or {}
        if not self.settings.get("default_chime_created"):
            if self.hub.chimes.get(DEFAULT_INTERCOM_CHIME) is None:
                try:
                    await self.hub.chimes.async_add(
                        DEFAULT_INTERCOM_CHIME, "intercom.wav", default_intercom_chime()
                    )
                except Exception:  # noqa: BLE001 - never block setup on this
                    _LOGGER.exception("Couldn't create the default intercom chime")
            self.settings.setdefault("intercom_chime", DEFAULT_INTERCOM_CHIME)
            self.settings["default_chime_created"] = True
            await self._store.async_save(self.settings)

    @property
    def chime_name(self) -> str | None:
        """The chime played before each message (None for no chime)."""
        return self.settings.get("intercom_chime", DEFAULT_INTERCOM_CHIME)

    async def async_set_chime(self, name: str | None) -> None:
        """Choose the intercom chime."""
        self.settings["intercom_chime"] = name
        await self._store.async_save(self.settings)

    def targets_for(self, sender: ConfigEntry) -> list[ConfigEntry]:
        """Loaded node entries the sender may talk to, never itself."""
        allowed = sender.options.get(CONF_INTERCOM_TARGETS, TARGETS_ALL)
        result = []
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == sender.entry_id or entry.state is not ConfigEntryState.LOADED:
                continue
            if allowed != TARGETS_ALL and entry.data[CONF_NODE_ID] not in allowed:
                continue
            result.append(entry)
        return result

    def _prune(self) -> None:
        now = dt_util.utcnow()
        for clip_id in list(self.clips):
            clip = self.clips[clip_id]
            if len(self.clips) > MAX_CLIPS or (now - clip.created).total_seconds() > CLIP_TTL_S:
                del self.clips[clip_id]
        live = set(self.clips)
        self._jobs = {j: v for j, v in self._jobs.items() if v[0] in live}

    async def async_receive(self, sender: ConfigEntry, data: bytes) -> Clip:
        """Accept a recording from a node and send it to its targets."""
        if len(data) > MAX_CLIP_BYTES:
            raise ClipError("clip too large")
        duration = wav_duration(data)
        if duration > MAX_CLIP_SECONDS + 1:
            raise ClipError("clip too long")

        clip = Clip(
            id=uuid.uuid4().hex,
            sender_id=sender.data[CONF_NODE_ID],
            sender_name=sender.title,
            created=dt_util.utcnow(),
            duration=round(duration, 1),
            data=data,
        )
        self.clips[clip.id] = clip
        self._prune()

        chime = self.hub.chimes.get(self.chime_name) if self.chime_name else None
        for entry in self.targets_for(sender):
            node_id = entry.data[CONF_NODE_ID]
            job_id = uuid.uuid4().hex
            sent = await self.hub.async_send(
                node_id,
                protocol.T_PLAY,
                job_id=job_id,
                kind=protocol.KIND_CLIP,
                clip_url=CLIP_PATH.format(clip_id=clip.id),
                pre_chime_hash=chime.hash if chime else None,
            )
            clip.deliveries[node_id] = {"name": entry.title, "status": "sent" if sent else "offline"}
            if sent:
                self._jobs[job_id] = (clip.id, node_id)

        device = dr.async_get(self.hass).async_get_device({(DOMAIN, clip.sender_id)})
        self.hass.bus.async_fire(
            EVENT_MESSAGE,
            {
                "sender": clip.sender_name,
                "sender_node_id": clip.sender_id,
                "sender_device_id": device.id if device else None,
                "duration": clip.duration,
                "recipients": [d["name"] for d in clip.deliveries.values() if d["status"] == "sent"],
                "offline": [d["name"] for d in clip.deliveries.values() if d["status"] == "offline"],
                "clip_id": clip.id,
            },
        )
        _LOGGER.info(
            "Intercom message from %s (%.1f s) to %s",
            clip.sender_name, clip.duration,
            ", ".join(d["name"] for d in clip.deliveries.values()) or "nobody",
        )
        return clip

    def job_update(self, node_id: str, job_id: str, status: str) -> None:
        """Record a node's progress playing a clip."""
        if (ref := self._jobs.get(job_id)) is None or ref[1] != node_id:
            return
        clip = self.clips.get(ref[0])
        if clip is not None and node_id in clip.deliveries:
            clip.deliveries[node_id]["status"] = status

    def get(self, clip_id: str) -> Clip | None:
        """A recent clip, if still held."""
        self._prune()
        return self.clips.get(clip_id)

    def recent(self) -> list[dict[str, Any]]:
        """Recent messages, newest first."""
        self._prune()
        return [c.summary() for c in reversed(self.clips.values())]
