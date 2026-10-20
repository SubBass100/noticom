"""Chimes and themes.

- A **sound** is an audio file in the library (the chimes folder, see
  chimes.py).
- A **chime** is a name automations use, like "doorbell". It never changes,
  so automations never need editing.
- A **theme** picks a sound for each chime. The Default theme is the catch
  all: any chime another theme leaves blank plays its Default sound.

Themes other than Default can have yearly date ranges ("10-01" to "10-31"),
optionally limited to hours of the day. When several match, the shortest
range wins; equal lengths go to the theme higher in the priority list. A
manual mode ("Automatic" or a theme) overrides the schedule.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .chimes import ChimeError, clean_name
from .const import DEFAULT_INTERCOM_CHIME, DOMAIN, STORAGE_VERSION

if TYPE_CHECKING:
    from .hub import NoticomHub

_LOGGER = logging.getLogger(__name__)

DEFAULT_THEME = "default"
MODE_AUTO = "auto"
INTERCOM_CHIME = DEFAULT_INTERCOM_CHIME  # built in: plays before intercom messages
SIGNAL_THEMES = f"{DOMAIN}_themes_updated"
MAX_THEME_NAME = 40
MAX_RANGES = 12

_DAY = re.compile(r"^(\d{2})-(\d{2})$")
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_LEAP = 2000  # reference year for day-of-year maths, so Feb 29 is valid


class ThemeError(ChimeError):
    """A theme operation failed; the message is shown to the user."""


def _day_of_year(mmdd: str) -> int:
    match = _DAY.match(mmdd or "")
    if not match:
        raise ThemeError(f"{mmdd!r} isn't a date (use MM-DD).")
    try:
        return date(_LEAP, int(match[1]), int(match[2])).timetuple().tm_yday
    except ValueError as err:
        raise ThemeError(f"{mmdd!r} isn't a real date.") from err


def _minutes(hhmm: str) -> int:
    match = _TIME.match(hhmm or "")
    if not match:
        raise ThemeError(f"{hhmm!r} isn't a time (use HH:MM).")
    return int(match[1]) * 60 + int(match[2])


def clean_range(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate one schedule range."""
    start, end = str(raw.get("start", "")), str(raw.get("end") or raw.get("start", ""))
    _day_of_year(start), _day_of_year(end)
    frm, to = raw.get("from") or None, raw.get("to") or None
    if (frm is None) != (to is None):
        raise ThemeError("Give both a start and an end time, or neither.")
    if frm is not None:
        if _minutes(frm) == _minutes(to):
            raise ThemeError("The start and end times are the same.")
    return {"start": start, "end": end, "from": frm, "to": to}


def range_days(rng: dict[str, Any]) -> int:
    """How many days a range covers (it may wrap past New Year)."""
    start, end = _day_of_year(rng["start"]), _day_of_year(rng["end"])
    return end - start + 1 if end >= start else 366 - start + end + 1


def _day_matches(rng: dict[str, Any], day: date) -> bool:
    today = (day.month, day.day)
    start = tuple(int(x) for x in rng["start"].split("-"))
    end = tuple(int(x) for x in rng["end"].split("-"))
    if start <= end:
        return start <= today <= end
    return today >= start or today <= end


def _time_matches(rng: dict[str, Any], now: datetime) -> bool:
    if not rng.get("from"):
        return True
    minute = now.hour * 60 + now.minute
    frm, to = _minutes(rng["from"]), _minutes(rng["to"])
    if frm < to:
        return frm <= minute < to
    return minute >= frm or minute < to  # overnight, e.g. 22:00-02:00


def range_matches(rng: dict[str, Any], now: datetime, use_time: bool = True) -> bool:
    """Whether a range covers this moment."""
    return _day_matches(rng, now.date()) and (not use_time or _time_matches(rng, now))


def clean_theme_name(name: str) -> str:
    """Theme names are display-only: any text up to 40 characters."""
    name = " ".join(str(name).split())
    if not name or len(name) > MAX_THEME_NAME:
        raise ThemeError(f"Theme names need 1 to {MAX_THEME_NAME} characters.")
    return name


class ThemeStore:
    """Chimes, themes, the schedule and the manual override."""

    def __init__(self, hass: HomeAssistant, hub: NoticomHub) -> None:
        self.hass = hass
        self.hub = hub
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.themes")
        self.chimes: list[str] = []
        self.default: dict[str, Any] = {}
        self.themes: list[dict[str, Any]] = []  # priority order, highest first
        self.mode: str = MODE_AUTO
        self._last_active: str | None = None

    # ---- loading and saving ----------------------------------------------

    async def async_load(self) -> None:
        """Load, or build from the existing chimes on first run after upgrading."""
        data = await self._store.async_load()
        if data is None:
            data = self._migrate()
            self._apply(data)
            await self.async_save()
            _LOGGER.info("Themes set up: %d chimes in the Default theme", len(self.chimes))
        else:
            self._apply(data)
        if self.chime_key(INTERCOM_CHIME) is None:  # always exists
            self.chimes.append(INTERCOM_CHIME)
            await self.async_save()
        self._last_active = self.active()[0]["id"]

    def _migrate(self) -> dict[str, Any]:
        """Each existing sound becomes a chime of the same name that plays it."""
        names = [c.name for c in self.hub.chimes.chimes]
        sounds = {n.lower(): n for n in names}
        intercom = self.hub.settings.get("intercom_chime", DEFAULT_INTERCOM_CHIME)
        if not any(n.lower() == INTERCOM_CHIME for n in names):
            names.append(INTERCOM_CHIME)
        sounds[INTERCOM_CHIME] = intercom if intercom and self.hub.chimes.get(intercom) else None
        return {
            "chimes": names,
            "default": {"id": DEFAULT_THEME, "name": "Default", "sounds": sounds, "tags": []},
            "themes": [],
            "mode": MODE_AUTO,
        }

    def _apply(self, data: dict[str, Any]) -> None:
        self.chimes = list(data.get("chimes", []))
        self.default = data.get("default") or {
            "id": DEFAULT_THEME, "name": "Default", "sounds": {}, "tags": []
        }
        self.themes = list(data.get("themes", []))
        self.mode = data.get("mode", MODE_AUTO)

    async def async_save(self) -> None:
        """Persist, then tell entities and the action dropdown."""
        await self._store.async_save(
            {
                "chimes": self.chimes,
                "default": self.default,
                "themes": self.themes,
                "mode": self.mode,
            }
        )
        self.notify()

    @callback
    def notify(self) -> None:
        """Refresh the Play chime dropdown and the theme entities."""
        from .services import async_update_chime_choices  # noqa: PLC0415 - import cycle

        async_update_chime_choices(self.hass, self.chime_names())
        self._last_active = self.active()[0]["id"]
        async_dispatcher_send(self.hass, SIGNAL_THEMES)

    @callback
    def check_active(self, _now: Any = None) -> None:
        """Called every minute: tell entities when the schedule switches theme."""
        active = self.active()[0]
        if active["id"] != self._last_active:
            _LOGGER.info("Theme is now %s", active["name"])
            self._last_active = active["id"]
            async_dispatcher_send(self.hass, SIGNAL_THEMES)

    # ---- lookups -----------------------------------------------------------

    def chime_names(self) -> list[str]:
        """All chime names, sorted."""
        return sorted(self.chimes, key=str.lower)

    def chime_key(self, name: str) -> str | None:
        """The chime's stored name (case-insensitive lookup), or None."""
        wanted = name.strip().lower()
        return next((c for c in self.chimes if c.lower() == wanted), None)

    def all_themes(self) -> list[dict[str, Any]]:
        """Default first, then the others in priority order."""
        return [self.default, *self.themes]

    def theme(self, theme_id: str) -> dict[str, Any]:
        """A theme by id. Raises ThemeError."""
        for theme in self.all_themes():
            if theme["id"] == theme_id:
                return theme
        raise ThemeError("That theme doesn't exist any more.")

    def _scheduled(self, now: datetime, use_time: bool = True) -> tuple[dict[str, Any], dict[str, Any]] | None:
        best: tuple[int, int, dict, dict] | None = None
        for priority, theme in enumerate(self.themes):
            for rng in theme.get("schedule", []):
                if range_matches(rng, now, use_time):
                    key = (range_days(rng), priority, theme, rng)
                    if best is None or key[:2] < best[:2]:
                        best = key
        return (best[2], best[3]) if best else None

    def active(self, now: datetime | None = None) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
        """(theme, reason, matching range). Reason: manual, schedule or default."""
        if self.mode != MODE_AUTO:
            try:
                return self.theme(self.mode), "manual", None
            except ThemeError:
                pass
        found = self._scheduled(now or dt_util.now())
        if found:
            return found[0], "schedule", found[1]
        return self.default, "default", None

    def sound_for(self, theme: dict[str, Any], chime: str) -> str | None:
        """The sound a theme picks for a chime (None: not set in that theme)."""
        key = self.chime_key(chime) or chime
        return theme.get("sounds", {}).get(key.lower())

    def resolve(self, chime: str, now: datetime | None = None) -> tuple[str | None, dict[str, Any]]:
        """The sound to play for a chime right now, and the theme it came from.

        The active theme's sound if it sets one, otherwise Default's.
        """
        theme = self.active(now)[0]
        if (sound := self.sound_for(theme, chime)) and self.hub.chimes.get(sound):
            return sound, theme
        sound = self.sound_for(self.default, chime)
        if sound and self.hub.chimes.get(sound):
            return sound, self.default
        return None, theme

    def sound_usage(self, sound: str) -> list[dict[str, str]]:
        """Where a sound is picked: [{theme_id, theme, chime}]."""
        wanted = sound.lower()
        used = []
        for theme in self.all_themes():
            for chime in self.chime_names():
                if (picked := theme["sounds"].get(chime.lower())) and picked.lower() == wanted:
                    used.append({"theme_id": theme["id"], "theme": theme["name"], "chime": chime})
        return used

    def sound_themes(self, sound: str) -> list[str]:
        """Theme ids a sound belongs to: picked anywhere in it, or tagged."""
        wanted = sound.lower()
        ids = {u["theme_id"] for u in self.sound_usage(sound)}
        for theme in self.all_themes():
            if any(t.lower() == wanted for t in theme.get("tags", [])):
                ids.add(theme["id"])
        return [t["id"] for t in self.all_themes() if t["id"] in ids]

    def calendar(self) -> list[dict[str, Any]]:
        """Which theme the schedule picks on each day of a year, as runs.

        Hours are ignored (a theme scheduled for evenings shows on its days).
        """
        runs: list[dict[str, Any]] = []
        for doy in range(1, 367):
            day = date.fromordinal(date(_LEAP, 1, 1).toordinal() + doy - 1)
            found = self._scheduled(datetime(day.year, day.month, day.day, 12), use_time=False)
            theme_id = found[0]["id"] if found else DEFAULT_THEME
            if runs and runs[-1]["theme_id"] == theme_id:
                runs[-1]["days"] += 1
                runs[-1]["end"] = day.strftime("%m-%d")
            else:
                runs.append(
                    {"theme_id": theme_id, "start": day.strftime("%m-%d"),
                     "end": day.strftime("%m-%d"), "days": 1}
                )
        return runs

    # ---- changes -------------------------------------------------------------

    def _sound_name(self, sound: str | None) -> str | None:
        if sound in (None, ""):
            return None
        found = self.hub.chimes.get(sound)
        if found is None:
            raise ThemeError(f"There's no sound called {sound!r}.")
        return found.name

    async def async_add_chime(self, name: str, sound: str | None = None) -> str:
        """Add a chime, optionally with its Default sound."""
        name = clean_name(name)
        if (existing := self.chime_key(name)) is not None:
            raise ThemeError(f"There's already a chime called {existing!r}.")
        sound = self._sound_name(sound)
        self.chimes.append(name)
        self.default["sounds"][name.lower()] = sound
        await self.async_save()
        return name

    async def async_delete_chime(self, name: str) -> None:
        """Remove a chime from every theme."""
        key = self.chime_key(name)
        if key is None:
            raise ThemeError(f"There's no chime called {name!r}.")
        if key.lower() == INTERCOM_CHIME:
            raise ThemeError("The intercom chime is built in. Set its sound to none instead.")
        self.chimes.remove(key)
        for theme in self.all_themes():
            theme["sounds"].pop(key.lower(), None)
        await self.async_save()

    async def async_set_sound(self, theme_id: str, chime: str, sound: str | None) -> None:
        """Pick a theme's sound for a chime (None: use Default / play nothing)."""
        theme = self.theme(theme_id)
        key = self.chime_key(chime)
        if key is None:
            raise ThemeError(f"There's no chime called {chime!r}.")
        sound = self._sound_name(sound)
        if sound is None and theme is not self.default:
            theme["sounds"].pop(key.lower(), None)
        else:
            theme["sounds"][key.lower()] = sound
        await self.async_save()

    async def async_add_theme(self, name: str) -> dict[str, Any]:
        """Add a theme at the bottom of the priority list."""
        name = clean_theme_name(name)
        if any(t["name"].lower() == name.lower() for t in self.all_themes()):
            raise ThemeError(f"There's already a theme called {name!r}.")
        theme = {"id": uuid.uuid4().hex[:10], "name": name, "sounds": {}, "tags": [], "schedule": []}
        self.themes.append(theme)
        await self.async_save()
        return theme

    async def async_update_theme(
        self, theme_id: str, name: str | None = None, schedule: list[dict] | None = None
    ) -> None:
        """Rename a theme or replace its schedule."""
        theme = self.theme(theme_id)
        if name is not None:
            if theme is self.default:
                raise ThemeError("The Default theme can't be renamed.")
            name = clean_theme_name(name)
            if any(
                t is not theme and t["name"].lower() == name.lower() for t in self.all_themes()
            ):
                raise ThemeError(f"There's already a theme called {name!r}.")
            theme["name"] = name
        if schedule is not None:
            if theme is self.default:
                raise ThemeError("The Default theme is used whenever no other theme is.")
            if len(schedule) > MAX_RANGES:
                raise ThemeError(f"Up to {MAX_RANGES} date ranges per theme.")
            theme["schedule"] = [clean_range(r) for r in schedule]
        await self.async_save()

    async def async_delete_theme(self, theme_id: str) -> None:
        """Delete a theme (its sounds stay in the library)."""
        theme = self.theme(theme_id)
        if theme is self.default:
            raise ThemeError("The Default theme can't be deleted.")
        self.themes.remove(theme)
        if self.mode == theme_id:
            self.mode = MODE_AUTO
        await self.async_save()

    async def async_reorder(self, order: list[str]) -> None:
        """Set the priority order (ids, highest first)."""
        by_id = {t["id"]: t for t in self.themes}
        if sorted(order) != sorted(by_id):
            raise ThemeError("The theme list changed; reload the page.")
        self.themes = [by_id[i] for i in order]
        await self.async_save()

    async def async_set_mode(self, mode: str) -> None:
        """Automatic (follow the schedule) or a theme id to force it."""
        if mode != MODE_AUTO:
            self.theme(mode)
        self.mode = mode
        await self.async_save()

    async def async_tag_sound(self, sound: str, theme_ids: list[str]) -> None:
        """Set which themes a sound is filed under (besides where it's picked)."""
        name = self._sound_name(sound)
        wanted = set(theme_ids)
        for theme in self.all_themes():
            tags = [t for t in theme.get("tags", []) if t.lower() != name.lower()]
            if theme["id"] in wanted:
                tags.append(name)
            theme["tags"] = tags
        await self.async_save()

    async def async_sound_deleted(self, sound: str) -> list[dict[str, str]]:
        """Forget a deleted sound everywhere. Returns where it was used."""
        used = self.sound_usage(sound)
        wanted = sound.lower()
        for theme in self.all_themes():
            for chime, picked in list(theme["sounds"].items()):
                if picked and picked.lower() == wanted:
                    if theme is self.default:
                        theme["sounds"][chime] = None
                    else:
                        del theme["sounds"][chime]
            theme["tags"] = [t for t in theme.get("tags", []) if t.lower() != wanted]
        await self.async_save()
        return used

    def problems(self) -> list[str]:
        """Chimes with no Default sound (they'd play nothing)."""
        return [
            c for c in self.chime_names()
            if c.lower() != INTERCOM_CHIME and not self.sound_for(self.default, c)
        ]
