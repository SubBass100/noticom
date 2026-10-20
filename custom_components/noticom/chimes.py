"""The sound library: the /config/noticom/chimes folder.

(Called "chimes" in code and the node protocol for history; the panel calls
them sounds. Chimes, the names automations use, are in themes.py.)

Drop WAV or MP3 files in the folder; the file name (without extension) is
the sound's name. Each file is normalized to mono 16-bit WAV, cached by its
SHA-256 hash, and synced to nodes by hash. The folder is rescanned
periodically and on `noticom.reload_chimes`.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from homeassistant.core import HomeAssistant

from .audio import ConversionError, convert
from .const import CHIME_CACHE_DIR, CHIME_DIR

_LOGGER = logging.getLogger(__name__)

EXTENSIONS = {".wav", ".mp3"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,47}$")


class ChimeError(Exception):
    """A chime operation failed; the message is shown to the user."""


def clean_name(name: str) -> str:
    """Validate a chime name: letters, digits, spaces, _ and -; max 48."""
    name = name.strip()
    if not NAME_RE.match(name):
        raise ChimeError(
            "Names can use letters, numbers, spaces, - and _ "
            "(start with a letter or number, up to 48 characters)."
        )
    return name


@dataclass(frozen=True)
class Chime:
    """One available chime."""

    name: str
    hash: str
    size: int
    path: Path  # the normalized WAV in the cache
    source: Path  # the file in the chimes folder
    duration: float  # seconds

    def manifest_entry(self) -> dict:
        """As listed in the `chimes` message."""
        return {"name": self.name, "hash": self.hash, "size": self.size}


class ChimeStore:
    """Scans the chime folder and keeps normalized copies."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.folder = Path(hass.config.path(CHIME_DIR))
        self.cache = Path(hass.config.path(CHIME_CACHE_DIR))
        self._chimes: dict[str, Chime] = {}  # lower-case name -> chime
        self._seen: dict[Path, tuple[tuple[int, int], Chime | None]] = {}
        self._lock = asyncio.Lock()

    @property
    def chimes(self) -> list[Chime]:
        """All chimes, sorted by name."""
        return sorted(self._chimes.values(), key=lambda c: c.name.lower())

    def manifest(self) -> list[dict]:
        """The chime list sent to nodes."""
        return [c.manifest_entry() for c in self.chimes]

    def get(self, name: str) -> Chime | None:
        """Look a chime up by name (case-insensitive)."""
        return self._chimes.get(name.strip().lower())

    def path_for_hash(self, chime_hash: str) -> Path | None:
        """The cached WAV for a hash, if it's a current chime."""
        for chime in self._chimes.values():
            if chime.hash == chime_hash:
                return chime.path
        return None

    async def async_scan(self) -> bool:
        """Rescan the folder. Returns True if the chime list changed."""
        async with self._lock:
            return await self.hass.async_add_executor_job(self._scan)

    async def async_add(self, name: str, filename: str, data: bytes, replace: bool = False) -> Chime:
        """Save an uploaded chime and load it. Raises ChimeError."""
        name = clean_name(name)
        ext = Path(filename).suffix.lower()
        if ext not in EXTENSIONS:
            raise ChimeError("Upload a WAV or MP3 file.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ChimeError("That file is over 10 MB; chimes should be short.")
        if (existing := self.get(name)) is not None and not replace:
            raise ChimeError(f"A chime named {existing.name!r} already exists.")
        async with self._lock:
            return await self.hass.async_add_executor_job(
                self._add, name, ext, data, existing
            )

    def _add(self, name: str, ext: str, data: bytes, existing: Chime | None) -> Chime:
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / f"{name}{ext}"
        staging = self.folder / f".upload-{name}{ext}"
        staging.write_bytes(data)
        try:
            chime = self._load(staging, name=name)
        except Exception:
            staging.unlink(missing_ok=True)
            raise
        if chime is None:
            staging.unlink(missing_ok=True)
            raise ChimeError("That file couldn't be read as audio.")
        if existing is not None and existing.source != target:
            existing.source.unlink(missing_ok=True)  # replacing e.g. .wav with .mp3
        staging.replace(target)
        self._scan()
        return self.get(name) or chime

    async def async_delete(self, name: str) -> None:
        """Delete a chime's file. Raises ChimeError if there's no such chime."""
        chime = self.get(name)
        if chime is None:
            raise ChimeError(f"No chime named {name!r}.")
        async with self._lock:
            await self.hass.async_add_executor_job(self._delete, chime)

    def _delete(self, chime: Chime) -> None:
        chime.source.unlink(missing_ok=True)
        self._scan()

    def _scan(self) -> bool:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        before = self.manifest()

        seen: dict[Path, tuple[tuple[int, int], Chime | None]] = {}
        chimes: dict[str, Chime] = {}
        for path in sorted(self.folder.iterdir()):
            if path.name.startswith(".") or path.suffix.lower() not in EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            signature = (stat.st_mtime_ns, stat.st_size)
            previous = self._seen.get(path)
            chime = previous[1] if previous and previous[0] == signature else None
            if chime is None and not (previous and previous[0] == signature):
                chime = self._load(path)
            seen[path] = (signature, chime)
            if chime is None:
                continue
            key = chime.name.lower()
            if key in chimes:
                _LOGGER.warning(
                    "Two chimes named %r; using %s and ignoring %s",
                    chime.name, chimes[key].name, path.name,
                )
                continue
            chimes[key] = chime

        self._seen, self._chimes = seen, chimes
        self._prune_cache()
        changed = self.manifest() != before
        if changed:
            _LOGGER.info("Chimes: %s", ", ".join(c.name for c in self.chimes) or "none")
        return changed

    def _load(self, path: Path, name: str | None = None) -> Chime | None:
        try:
            wav = convert(path)
        except ConversionError as err:
            _LOGGER.warning("Skipping chime %s: %s", path.name, err)
            return None
        digest = hashlib.sha256(wav).hexdigest()
        cached = self.cache / f"{digest}.wav"
        if not cached.exists():
            tmp = cached.with_suffix(".tmp")
            tmp.write_bytes(wav)
            tmp.replace(cached)
        rate = int.from_bytes(wav[24:28], "little") or 1
        duration = max(0, len(wav) - 44) / 2 / rate
        return Chime(
            name=name or path.stem,
            hash=digest,
            size=len(wav),
            path=cached,
            source=path,
            duration=round(duration, 2),
        )

    def _prune_cache(self) -> None:
        keep = {c.path.name for c in self._chimes.values()}
        for path in self.cache.glob("*.wav"):
            if path.name not in keep:
                path.unlink(missing_ok=True)
