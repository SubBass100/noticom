"""The Noticom sidebar panel and its admin-only API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import (
    KEY_HASS,
    KEY_HASS_USER,
    HomeAssistantView,
    StaticPathConfig,
)
from homeassistant.core import HomeAssistant, callback

from homeassistant.config_entries import ConfigEntryState

from .chimes import MAX_UPLOAD_BYTES, ChimeError
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_INTERCOM_TARGETS,
    CONF_NODE_ID,
    CONF_PTT_ENABLED,
    DOMAIN,
    INSTALL_COMMAND,
    INSTALL_COMMAND_NO_BUTTON,
    PAIR_COMMAND,
)
from .hub import NoticomHub, node_caps, node_options
from .intercom import TARGETS_ALL
from .themes import INTERCOM_CHIME
from .usage import find_usage

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "noticom"
STATIC_URL = "/noticom_static"
UPLOAD_PATH = "/api/noticom/panel/sounds"
PREVIEW_PATH = "/api/noticom/panel/sound/{chime_hash}"
CLIP_PREVIEW_PATH = "/api/noticom/panel/clip/{clip_id}"
FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Serve the panel's JS, register it in the sidebar, and add its API."""
    version = (FRONTEND_DIR / "noticom-panel.js").stat().st_mtime_ns
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
    )
    # Load the Noticom icon set on every page so the sidebar can show it.
    icons_version = (FRONTEND_DIR / "noticom-icons.js").stat().st_mtime_ns
    sidebar_icon = "mdi:bullhorn-variant"
    try:
        frontend.add_extra_js_url(hass, f"{STATIC_URL}/noticom-icons.js?v={icons_version}")
        sidebar_icon = "noticom:logo"
    except KeyError:  # frontend not loaded (e.g. in tests): keep the stock icon
        _LOGGER.debug("Frontend not loaded; using the default sidebar icon")
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="noticom-panel",
        sidebar_title="Noticom",
        sidebar_icon=sidebar_icon,
        module_url=f"{STATIC_URL}/noticom-panel.js?v={version}",
        require_admin=True,
    )
    hass.http.register_view(ChimeUploadView())
    hass.http.register_view(ChimePreviewView())
    hass.http.register_view(ClipPreviewView())
    websocket_api.async_register_command(hass, ws_list_sounds)
    websocket_api.async_register_command(hass, ws_delete_sound)
    websocket_api.async_register_command(hass, ws_tag_sound)
    for command in THEME_COMMANDS:
        websocket_api.async_register_command(hass, command)
    websocket_api.async_register_command(hass, ws_intercom_get)
    websocket_api.async_register_command(hass, ws_intercom_set_chime)
    websocket_api.async_register_command(hass, ws_intercom_set_targets)
    websocket_api.async_register_command(hass, ws_settings_get)
    websocket_api.async_register_command(hass, ws_settings_set)
    websocket_api.async_register_command(hass, ws_nodes_update)


def sound_list(hub: NoticomHub) -> list[dict[str, Any]]:
    """The sound library as the panel shows it."""
    return [
        {
            "name": c.name,
            "hash": c.hash,
            "duration": c.duration,
            "file": c.source.name,
            "themes": hub.themes.sound_themes(c.name),
            "used": hub.themes.sound_usage(c.name),
        }
        for c in hub.chimes.chimes
    ]


def _require_admin(request: web.Request) -> web.Response | None:
    user = request.get(KEY_HASS_USER)
    if user is None or not user.is_admin:
        return web.json_response({"error": "Admin only."}, status=403)
    return None


class ChimeUploadView(HomeAssistantView):
    """POST multipart to add a sound.

    Fields: file, name, replace ("true"), make_chime ("true": also add a chime
    of the same name that plays it), themes (comma-separated theme ids to
    file it under).
    """

    url = UPLOAD_PATH
    name = "api:noticom:panel:sounds"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        if (denied := _require_admin(request)) is not None:
            return denied
        hass = request.app[KEY_HASS]
        hub: NoticomHub = hass.data[DOMAIN]
        fields: dict[str, str] = {}
        filename, data = "", b""
        try:
            reader = await request.multipart()
            while (part := await reader.next()) is not None:
                if part.name == "file":
                    filename = part.filename or ""
                    data = await part.read(decode=False)
                    if len(data) > MAX_UPLOAD_BYTES:
                        break
                elif part.name:
                    fields[part.name] = await part.text()
        except (ValueError, AssertionError):
            return web.json_response({"error": "Bad upload."}, status=400)
        if not data:
            return web.json_response({"error": "Choose a file to upload."}, status=400)
        name = fields.get("name") or Path(filename).stem
        theme_ids = [t for t in fields.get("themes", "").split(",") if t]
        try:
            for theme_id in theme_ids:
                hub.themes.theme(theme_id)  # check before saving anything
            sound = await hub.chimes.async_add(
                name, filename, data, replace=fields.get("replace") == "true"
            )
        except ChimeError as err:
            return web.json_response({"error": str(err)}, status=400)
        await hub.async_broadcast_chimes()
        made_chime = None
        if fields.get("make_chime") == "true" and hub.themes.chime_key(sound.name) is None:
            made_chime = await hub.themes.async_add_chime(sound.name, sound.name)
        if theme_ids:
            await hub.themes.async_tag_sound(
                sound.name, sorted(set(theme_ids) | set(hub.themes.sound_themes(sound.name)))
            )
        _LOGGER.info("Sound %s uploaded", sound.name)
        return web.json_response(
            {"sound": sound.name, "chime": made_chime, "sounds": sound_list(hub)}
        )


class ChimePreviewView(HomeAssistantView):
    """GET a sound's normalized WAV for the panel's preview button."""

    url = PREVIEW_PATH
    name = "api:noticom:panel:sound"
    requires_auth = True

    async def get(self, request: web.Request, chime_hash: str) -> web.StreamResponse:
        if (denied := _require_admin(request)) is not None:
            return denied
        path = request.app[KEY_HASS].data[DOMAIN].chimes.path_for_hash(chime_hash)
        if path is None:
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Content-Type": "audio/wav"})


def _themes_brief(hub: NoticomHub) -> list[dict[str, str]]:
    return [{"id": t["id"], "name": t["name"]} for t in hub.themes.all_themes()]


@websocket_api.websocket_command({vol.Required("type"): "noticom/sounds/list"})
@websocket_api.require_admin
@callback
def ws_list_sounds(hass: HomeAssistant, connection, msg: dict) -> None:
    """The sound library, and the themes to filter by."""
    hub: NoticomHub = hass.data[DOMAIN]
    connection.send_result(msg["id"], {"sounds": sound_list(hub), "themes": _themes_brief(hub)})


@websocket_api.websocket_command(
    {vol.Required("type"): "noticom/sounds/delete", vol.Required("name"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_delete_sound(hass: HomeAssistant, connection, msg: dict) -> None:
    """Delete a sound; themes that used it fall back to Default."""
    hub: NoticomHub = hass.data[DOMAIN]
    sound = hub.chimes.get(msg["name"])
    try:
        await hub.chimes.async_delete(msg["name"])
    except ChimeError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    used = await hub.themes.async_sound_deleted(sound.name if sound else msg["name"])
    await hub.async_broadcast_chimes()
    _LOGGER.info("Sound %s deleted", msg["name"])
    connection.send_result(
        msg["id"], {"sounds": sound_list(hub), "themes": _themes_brief(hub), "was_used": used}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "noticom/sounds/tag",
        vol.Required("name"): str,
        vol.Required("themes"): [str],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_tag_sound(hass: HomeAssistant, connection, msg: dict) -> None:
    """File a sound under themes."""
    hub: NoticomHub = hass.data[DOMAIN]
    try:
        for theme_id in msg["themes"]:
            hub.themes.theme(theme_id)
        await hub.themes.async_tag_sound(msg["name"], msg["themes"])
    except ChimeError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {"sounds": sound_list(hub), "themes": _themes_brief(hub)})


class ClipPreviewView(HomeAssistantView):
    """GET a recent intercom message for the panel's play button."""

    url = CLIP_PREVIEW_PATH
    name = "api:noticom:panel:clip"
    requires_auth = True

    async def get(self, request: web.Request, clip_id: str) -> web.Response:
        if (denied := _require_admin(request)) is not None:
            return denied
        clip = request.app[KEY_HASS].data[DOMAIN].intercom.get(clip_id)
        if clip is None:
            return web.Response(status=404)
        return web.Response(body=clip.data, content_type="audio/wav")


def intercom_state(hass: HomeAssistant) -> dict[str, Any]:
    """Everything the Intercom tab shows."""
    hub: NoticomHub = hass.data[DOMAIN]
    nodes = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        opts = node_options(entry)
        caps = node_caps(entry)
        node_id = entry.data[CONF_NODE_ID]
        nodes.append(
            {
                "node_id": node_id,
                "name": entry.title,
                "connected": hub.is_connected(node_id),
                "can_talk": bool(caps["mic"] and caps["button"]),
                "ptt_enabled": opts[CONF_PTT_ENABLED],
                "targets": entry.options.get(CONF_INTERCOM_TARGETS, TARGETS_ALL),
            }
        )
    nodes.sort(key=lambda n: n["name"].lower())
    return {
        "chime": hub.intercom.chime_name,
        "chimes": [c.name for c in hub.chimes.chimes],
        "nodes": nodes,
        "messages": hub.intercom.recent(),
    }


@websocket_api.websocket_command({vol.Required("type"): "noticom/intercom/get"})
@websocket_api.require_admin
@callback
def ws_intercom_get(hass: HomeAssistant, connection, msg: dict) -> None:
    """Intercom settings, nodes and recent messages."""
    connection.send_result(msg["id"], intercom_state(hass))


@websocket_api.websocket_command(
    {vol.Required("type"): "noticom/intercom/set_chime", vol.Required("chime"): vol.Any(None, str)}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_intercom_set_chime(hass: HomeAssistant, connection, msg: dict) -> None:
    """Choose the chime played before intercom messages (null for none)."""
    hub: NoticomHub = hass.data[DOMAIN]
    name = msg["chime"]
    if name is not None:
        chime = hub.chimes.get(name)
        if chime is None:
            connection.send_error(msg["id"], "not_found", f"No chime named {name!r}.")
            return
        name = chime.name
    await hub.intercom.async_set_chime(name)
    connection.send_result(msg["id"], intercom_state(hass))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "noticom/intercom/set_targets",
        vol.Required("node_id"): str,
        vol.Required("targets"): vol.Any(TARGETS_ALL, [str]),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_intercom_set_targets(hass: HomeAssistant, connection, msg: dict) -> None:
    """Set which nodes a node's button talks to ("all" or a list of node ids)."""
    entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, msg["node_id"])
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No such node.")
        return
    targets = msg["targets"]
    if targets != TARGETS_ALL:
        known = {e.data[CONF_NODE_ID] for e in hass.config_entries.async_entries(DOMAIN)}
        targets = sorted(set(targets) & known - {msg["node_id"]})
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_INTERCOM_TARGETS: targets}
    )
    connection.send_result(msg["id"], intercom_state(hass))


NODE_DEFAULTS_SCHEMA = vol.Schema(
    {
        vol.Required("volume"): vol.All(int, vol.Range(min=0, max=100)),
        vol.Required("mic_gain"): vol.All(int, vol.Range(min=0, max=100)),
        vol.Required("mic_boost"): vol.All(int, vol.Range(min=0, max=3)),
        vol.Required("ptt_enabled"): bool,
        vol.Required("button_pin"): vol.All(int, vol.Range(min=0, max=27)),  # 0: no button
        vol.Required("button_nc"): bool,
        vol.Required("intercom_targets"): vol.Any(TARGETS_ALL, vol.All([str], vol.Length(max=0))),
    }
)


def settings_state(hub: NoticomHub) -> dict[str, Any]:
    """Integration-wide settings shown on the Settings tab."""
    defaults = hub.node_defaults
    return {
        "commands": {
            "install": INSTALL_COMMAND,
            "install_no_button": INSTALL_COMMAND_NO_BUTTON,
            "pair": PAIR_COMMAND,
        },
        "software": software_state(hub),
        "chime_priority": hub.chime_priority,
        "node_defaults": {str(k): defaults[str(k)] for k in NODE_DEFAULTS_SCHEMA.schema},
    }


@websocket_api.websocket_command({vol.Required("type"): "noticom/settings/get"})
@websocket_api.require_admin
@callback
def ws_settings_get(hass: HomeAssistant, connection, msg: dict) -> None:
    """Global settings and defaults for new nodes."""
    connection.send_result(msg["id"], settings_state(hass.data[DOMAIN]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "noticom/settings/set",
        vol.Optional("chime_priority"): bool,
        vol.Optional("node_defaults"): NODE_DEFAULTS_SCHEMA,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_settings_set(hass: HomeAssistant, connection, msg: dict) -> None:
    """Save global settings; a chime-priority change reaches nodes immediately."""
    hub: NoticomHub = hass.data[DOMAIN]
    priority_changed = False
    if "chime_priority" in msg:
        priority_changed = msg["chime_priority"] != hub.chime_priority
        hub.settings["chime_priority"] = msg["chime_priority"]
    if "node_defaults" in msg:
        hub.settings["node_defaults"] = dict(msg["node_defaults"])
    await hub.async_save_settings()
    if priority_changed:
        await hub.async_push_config_all()
    connection.send_result(msg["id"], settings_state(hub))


def software_state(hub: NoticomHub) -> dict[str, Any]:
    """Newest node version and what each node runs."""
    nodes = []
    for entry in hub.hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        node_id = entry.data[CONF_NODE_ID]
        nodes.append(
            {
                "node_id": node_id,
                "name": entry.title,
                "connected": hub.is_connected(node_id),
                "version": hub.software.installed(entry),
                "update_available": hub.software.update_available(entry),
                "remote_update": hub.software.can_update_remotely(entry),
                "updating": hub.software.in_progress(node_id),
            }
        )
    nodes.sort(key=lambda n: n["name"].lower())
    return {"latest": hub.software.latest, "nodes": nodes}


@websocket_api.websocket_command(
    {vol.Required("type"): "noticom/nodes/update", vol.Optional("node_ids"): [str]}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_nodes_update(hass: HomeAssistant, connection, msg: dict) -> None:
    """Update the given nodes, or every online node that's out of date."""
    hub: NoticomHub = hass.data[DOMAIN]
    wanted = set(msg.get("node_ids") or [])
    started, skipped = [], []
    for node in software_state(hub)["nodes"]:
        if wanted and node["node_id"] not in wanted:
            continue
        if not wanted and not node["update_available"]:
            continue
        if node["updating"]:
            continue
        if not node["remote_update"]:
            skipped.append(node["name"])
            continue
        try:
            await hub.software.async_update(node["node_id"])
        except HomeAssistantError:
            skipped.append(node["name"])
        else:
            started.append(node["name"])
    connection.send_result(
        msg["id"], {"started": started, "skipped": skipped, "software": software_state(hub)}
    )


# ---- Themes tab ------------------------------------------------------------


def themes_state(hass: HomeAssistant) -> dict[str, Any]:
    """Everything the Themes tab shows."""
    hub: NoticomHub = hass.data[DOMAIN]
    themes = hub.themes
    active, reason, rng = themes.active()

    used_by: dict[str, list[dict[str, Any]]] = {c.lower(): [] for c in themes.chimes}
    unknown, dynamic, direct = [], [], []
    for use in find_usage(hass):
        ref = {"name": use["name"], "kind": use["kind"], "edit": use["edit"],
               "entity_id": use["entity_id"]}
        for chime in use["chimes"]:
            if chime is None:
                dynamic.append(ref)
            elif chime.startswith("sound:"):
                direct.append({**ref, "sound": chime[6:]})
            elif (key := themes.chime_key(chime)) is not None:
                used_by[key.lower()].append(ref)
            elif hub.chimes.get(chime) is not None:
                direct.append({**ref, "sound": chime})
            else:
                unknown.append({**ref, "chime": chime})
    used_by.setdefault(INTERCOM_CHIME, []).insert(
        0, {"name": "Intercom messages", "kind": "builtin", "edit": None, "entity_id": None}
    )

    return {
        "mode": themes.mode,
        "active": {"id": active["id"], "name": active["name"], "reason": reason, "range": rng},
        "themes": [
            {
                "id": t["id"],
                "name": t["name"],
                "default": t is themes.default,
                "schedule": t.get("schedule", []),
            }
            for t in themes.all_themes()
        ],
        "chimes": [
            {
                "name": c,
                "builtin": c.lower() == INTERCOM_CHIME,
                "sounds": {t["id"]: themes.sound_for(t, c) for t in themes.all_themes()},
                "used_by": used_by.get(c.lower(), []),
            }
            for c in themes.chime_names()
        ],
        "sounds": [
            {"name": c.name, "hash": c.hash, "themes": themes.sound_themes(c.name)}
            for c in hub.chimes.chimes
        ],
        "missing": themes.problems(),
        "unknown": unknown,
        "dynamic": dynamic,
        "direct": direct,
        "calendar": themes.calendar(),
    }


def _theme_command(schema: dict, handler):
    """Register-able WS command that runs a theme change, then returns the state."""

    @websocket_api.websocket_command(schema)
    @websocket_api.require_admin
    @websocket_api.async_response
    async def command(hass: HomeAssistant, connection, msg: dict) -> None:
        try:
            await handler(hass.data[DOMAIN].themes, msg)
        except ChimeError as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        connection.send_result(msg["id"], themes_state(hass))

    return command


async def _noop(themes, msg) -> None:
    return None


RANGE_SCHEMA = vol.Schema(
    {
        vol.Required("start"): str,
        vol.Required("end"): str,
        vol.Optional("from"): vol.Any(None, str),
        vol.Optional("to"): vol.Any(None, str),
    }
)

THEME_COMMANDS = [
    _theme_command({vol.Required("type"): "noticom/themes/get"}, _noop),
    _theme_command(
        {
            vol.Required("type"): "noticom/themes/set_sound",
            vol.Required("theme_id"): str,
            vol.Required("chime"): str,
            vol.Required("sound"): vol.Any(None, str),
        },
        lambda t, m: t.async_set_sound(m["theme_id"], m["chime"], m["sound"]),
    ),
    _theme_command(
        {
            vol.Required("type"): "noticom/themes/add_chime",
            vol.Required("name"): str,
            vol.Optional("sound"): vol.Any(None, str),
        },
        lambda t, m: t.async_add_chime(m["name"], m.get("sound")),
    ),
    _theme_command(
        {vol.Required("type"): "noticom/themes/delete_chime", vol.Required("name"): str},
        lambda t, m: t.async_delete_chime(m["name"]),
    ),
    _theme_command(
        {vol.Required("type"): "noticom/themes/add", vol.Required("name"): str},
        lambda t, m: t.async_add_theme(m["name"]),
    ),
    _theme_command(
        {
            vol.Required("type"): "noticom/themes/update",
            vol.Required("theme_id"): str,
            vol.Optional("name"): str,
            vol.Optional("schedule"): [RANGE_SCHEMA],
        },
        lambda t, m: t.async_update_theme(m["theme_id"], m.get("name"), m.get("schedule")),
    ),
    _theme_command(
        {vol.Required("type"): "noticom/themes/delete", vol.Required("theme_id"): str},
        lambda t, m: t.async_delete_theme(m["theme_id"]),
    ),
    _theme_command(
        {vol.Required("type"): "noticom/themes/reorder", vol.Required("order"): [str]},
        lambda t, m: t.async_reorder(m["order"]),
    ),
    _theme_command(
        {vol.Required("type"): "noticom/themes/set_mode", vol.Required("mode"): str},
        lambda t, m: t.async_set_mode(m["mode"]),
    ),
]
