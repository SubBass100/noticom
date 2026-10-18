"""Chime storage: the /config/noticom/chimes folder.

Drop WAV or MP3 files in the folder; the file name (without extension) is
the chime's name. Each file is normalized to mono 16-bit WAV, cached by its
SHA-256 hash, and synced to nodes by hash. The folder is rescanned
periodically and on `noticom.reload_chimes`.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from homeassistant.core import HomeAssistant

from .audio import ConversionError, convert
from .const import CHIME_CACHE_DIR, CHIME_DIR

_LOGGER = logging.getLogger(__name__)

EXTENSIONS = {".wav", ".mp3"}


@dataclass(frozen=True)
class Chime:
    """One available chime."""

    name: str
    hash: str
    size: int
    path: Path  # the normalized WAV in the cache

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
        return await self.hass.async_add_executor_job(self._scan)

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

    def _load(self, path: Path) -> Chime | None:
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
        return Chime(name=path.stem, hash=digest, size=len(wav), path=cached)

    def _prune_cache(self) -> None:
        keep = {c.path.name for c in self._chimes.values()}
        for path in self.cache.glob("*.wav"):
            if path.name not in keep:
                path.unlink(missing_ok=True)
