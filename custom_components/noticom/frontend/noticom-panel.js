// Noticom sidebar panel. Plain web component, no build step.
// Uses Home Assistant's theme variables so it follows light/dark themes.

const UPLOAD_URL = "/api/noticom/panel/sounds";
const PREVIEW_URL = (hash) => `/api/noticom/panel/sound/${hash}`;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
// Theme colours (Default is grey). Mid-tone so they read on light and dark.
const PALETTE = ["#e8710a", "#d01884", "#1a73e8", "#188038", "#9334e6", "#c5221f", "#129eaf", "#b06000"];
const fmtDay = (mmdd) => {
  const [m, d] = mmdd.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}`;
};
const fmtTime = (hhmm) => {
  const [h, m] = hhmm.split(":").map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString([], { hour: "numeric", minute: m ? "2-digit" : undefined });
};
const fmtRange = (r) =>
  (r.start === r.end ? fmtDay(r.start) : `${fmtDay(r.start)} – ${fmtDay(r.end)}`) +
  (r.from ? `, ${fmtTime(r.from)} – ${fmtTime(r.to)}` : "");
const CLIP_URL = (id) => `/api/noticom/panel/clip/${id}`;
const STATUS = {
  sent: "Sending", started: "Playing", done: "Played",
  dropped: "Skipped (queue full)", error: "Failed", offline: "Offline",
};

const ago = (iso) => {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
};
const ACCEPT = ".wav,.mp3,audio/wav,audio/x-wav,audio/mpeg";
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,47}$/;

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const suggestName = (filename) =>
  filename
    .replace(/\.[^.]+$/, "")
    .replace(/[^A-Za-z0-9 _-]+/g, "_")
    .replace(/^[^A-Za-z0-9]+/, "")
    .slice(0, 48);

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, var(--ha-font-family-body, system-ui, sans-serif));
    -webkit-font-smoothing: antialiased;
  }
  .toolbar {
    display: flex; align-items: center; gap: 4px;
    height: var(--header-height, 56px); padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    border-bottom: var(--app-header-border-bottom, none);
    position: sticky; top: 0; z-index: 2;
  }
  .toolbar h1 { font-size: 20px; font-weight: 400; margin: 0 0 0 8px; }
  main { max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }
  .tabs {
    display: flex; gap: 4px; padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    position: sticky; top: var(--header-height, 56px); z-index: 2;
  }
  .tab {
    height: 48px; border-radius: 0; padding: 0 16px; color: inherit; opacity: .75;
    border-bottom: 2px solid transparent; font-size: 14px; letter-spacing: .04em;
  }
  .tab:hover { background: rgba(255,255,255,.08); opacity: 1; }
  .tab[aria-selected="true"] { opacity: 1; border-bottom-color: currentColor; }
  select {
    font: inherit; font-size: 16px; color: var(--primary-text-color);
    background: var(--input-fill-color, var(--secondary-background-color, rgba(0,0,0,.04)));
    border: 1px solid var(--divider-color, rgba(0,0,0,.2)); border-radius: 8px;
    padding: 9px 10px; min-width: 0; max-width: 100%;
  }
  select:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; }
  .pad { padding: 16px; }
  .setting { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .setting .title { font-size: 16px; }
  .node { padding: 14px 16px; }
  .node + .node { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .node-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: space-between; }
  .node-name { display: flex; align-items: center; gap: 8px; font-size: 16px; min-width: 0; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--disabled-color, #bdbdbd); flex-shrink: 0; }
  .dot.on { background: var(--success-color, #43a047); }
  .badge { font-size: 12px; color: var(--secondary-text-color); border: 1px solid var(--divider-color, rgba(0,0,0,.2)); border-radius: 10px; padding: 1px 8px; }
  .picks { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 10px; padding-left: 16px; }
  .picks label { display: flex; align-items: center; gap: 6px; font-size: 14px; }
  .recips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
  .chip { font-size: 12px; border-radius: 10px; padding: 1px 8px; background: var(--secondary-background-color, rgba(0,0,0,.06)); color: var(--secondary-text-color); }
  .chip.done { color: var(--success-color, #43a047); }
  .chip.error, .chip.offline, .chip.dropped { color: var(--error-color, #db4437); }
  .form { display: grid; grid-template-columns: minmax(140px, 220px) 1fr; gap: 14px 20px; align-items: center; padding: 16px; }
  .form > label { font-size: 15px; }
  .form .ctl { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .form input[type=range] { flex: 1; min-width: 0; accent-color: var(--primary-color); }
  .form input[type=number] { width: 90px; font: inherit; font-size: 16px; color: var(--primary-text-color);
    background: var(--input-fill-color, var(--secondary-background-color, rgba(0,0,0,.04)));
    border: 1px solid var(--divider-color, rgba(0,0,0,.2)); border-radius: 8px; padding: 9px 10px; }
  .form .val { width: 3.2em; text-align: right; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .form-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 16px 16px; flex-wrap: wrap; }
  .switch-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .cmds { padding: 4px 16px 16px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; }
  .cmds > div { min-width: 0; }
  .cmd-label { font-size: 14px; margin-bottom: 6px; }
  .cmd { display: flex; align-items: stretch; gap: 8px; }
  .cmd code {
    flex: 1; min-width: 0; display: block; padding: 10px 12px; border-radius: 8px;
    background: var(--secondary-background-color, rgba(0,0,0,.05));
    border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    font-size: 13px; line-height: 1.45; overflow-x: auto; white-space: nowrap;
    user-select: all; -webkit-user-select: all;
  }
  .cmd button { flex-shrink: 0; align-self: center; }
  .sw-row { display: flex; align-items: center; gap: 12px; padding: 10px 8px 10px 16px; }
  .sw-row + .sw-row { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .sw-row .grow { flex: 1; min-width: 0; }
  .ok { color: var(--success-color, #43a047); }
  .warn { color: var(--warning-color, #ffa600); }
  input[type=checkbox] { accent-color: var(--primary-color); width: 18px; height: 18px; flex-shrink: 0; }
  @media (max-width: 600px) {
    .form { grid-template-columns: 1fr; gap: 6px; }
    .form > label { margin-top: 8px; color: var(--secondary-text-color); font-size: 13px; }
  }
  .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 0 4px 12px; }
  h2 { font-size: 22px; font-weight: 400; margin: 0; }
  .hint { color: var(--secondary-text-color); font-size: 14px; line-height: 1.5; }
  .card {
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    box-shadow: var(--ha-card-box-shadow, none);
    margin-bottom: 24px; overflow: hidden;
  }

  /* Upload */
  .upload { padding: 16px; display: grid; gap: 14px; }
  .drop {
    border: 2px dashed var(--divider-color, rgba(0,0,0,.2));
    border-radius: 10px; padding: 22px 16px; text-align: center; cursor: pointer;
    transition: border-color .15s, background-color .15s;
  }
  .drop:hover, .drop:focus-visible, .drop.dragging {
    border-color: var(--primary-color);
    background: color-mix(in srgb, var(--primary-color) 7%, transparent);
    outline: none;
  }
  .drop ha-icon { --mdc-icon-size: 32px; color: var(--primary-color); display: block; margin: 0 auto 6px; }
  .drop strong { display: block; font-weight: 500; margin-bottom: 2px; word-break: break-all; }
  .row { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
  label.field { flex: 1 1 220px; display: grid; gap: 6px; font-size: 13px; color: var(--secondary-text-color); }
  input[type=text] {
    font: inherit; font-size: 16px; color: var(--primary-text-color);
    background: var(--input-fill-color, var(--secondary-background-color, rgba(0,0,0,.04)));
    border: 1px solid var(--divider-color, rgba(0,0,0,.2));
    border-radius: 8px; padding: 10px 12px; min-width: 0;
  }
  input[type=text]:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; border-color: transparent; }
  .replace { display: flex; align-items: center; gap: 8px; font-size: 14px; }
  [hidden] { display: none !important; }
  .msg { font-size: 14px; min-height: 1.2em; }
  .msg.error { color: var(--error-color, #db4437); }

  button {
    font: inherit; font-size: 14px; font-weight: 500; letter-spacing: .02em;
    border: none; border-radius: 18px; padding: 0 16px; height: 36px; cursor: pointer;
    display: inline-flex; align-items: center; gap: 6px;
    background: transparent; color: var(--primary-color);
  }
  button ha-icon { --mdc-icon-size: 18px; }
  button:hover { background: color-mix(in srgb, var(--primary-color) 10%, transparent); }
  button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  button.primary:hover { filter: brightness(1.08); }
  button.danger { color: var(--error-color, #db4437); }
  button.danger:hover { background: color-mix(in srgb, var(--error-color, #db4437) 10%, transparent); }
  button:disabled { opacity: .45; cursor: default; filter: none; background: transparent; }
  button.primary:disabled { background: var(--disabled-color, #bdbdbd); color: #fff; }

  /* List */
  .list-head { padding: 14px 16px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.12)); display: flex; justify-content: space-between; align-items: center; }
  .count { color: var(--secondary-text-color); font-size: 14px; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: flex; align-items: center; gap: 12px; padding: 10px 8px 10px 16px; }
  li + li { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .info { flex: 1; min-width: 0; }
  .name { font-size: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { color: var(--secondary-text-color); font-size: 13px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  code { font-family: var(--code-font-family, ui-monospace, monospace); font-size: 12.5px; }
  .actions { display: flex; gap: 2px; flex-shrink: 0; }
  .empty { padding: 32px 16px; text-align: center; color: var(--secondary-text-color); }
  .empty ha-icon { --mdc-icon-size: 40px; display: block; margin: 0 auto 8px; opacity: .6; }

  /* Themes */
  .now { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding: 16px; }
  .now-title { font-size: 20px; display: flex; align-items: center; gap: 10px; }
  .swatch { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; display: inline-block; }
  .year { padding: 0 16px 16px; }
  .strip { display: flex; height: 18px; border-radius: 6px; overflow: hidden; background: var(--secondary-background-color, rgba(0,0,0,.06)); position: relative; }
  .strip span { height: 100%; }
  .strip .today { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--primary-text-color); }
  .months { display: flex; font-size: 11px; color: var(--secondary-text-color); margin-top: 4px; }
  .months span { flex: 1; text-align: left; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 10px; font-size: 13px; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .warnbox { padding: 12px 16px; border-left: 4px solid var(--warning-color, #ffa600); }
  .warnbox + .warnbox { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .warnbox .title { font-weight: 500; margin-bottom: 4px; }
  .grid-wrap { overflow-x: auto; }
  table.grid { border-collapse: collapse; width: 100%; font-size: 14px; }
  .grid th, .grid td { padding: 8px 10px; text-align: left; vertical-align: top; border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .grid thead th { border-top: none; font-weight: 500; white-space: nowrap; color: var(--secondary-text-color); }
  .grid thead th.on { color: var(--primary-text-color); }
  .grid th:first-child, .grid td:first-child {
    position: sticky; left: 0; z-index: 1; min-width: 150px; max-width: 220px;
    background: var(--ha-card-background, var(--card-background-color, #fff));
  }
  .grid td.on { background: color-mix(in srgb, var(--primary-color) 6%, transparent); }
  .grid .cell { display: flex; align-items: center; gap: 2px; }
  .grid select { font-size: 14px; padding: 6px 8px; min-width: 120px; width: 100%; }
  .grid .cell { min-width: 150px; }
  .theme-row .meta { white-space: normal; }
  .grid select.inherit { color: var(--secondary-text-color); font-style: italic; }
  button.mini { height: 32px; width: 32px; padding: 0; justify-content: center; }
  .chime-name { font-size: 15px; font-weight: 500; display: flex; align-items: center; gap: 4px; }
  .used { font-size: 12px; color: var(--secondary-text-color); margin-top: 3px; line-height: 1.5; }
  .used a { color: var(--primary-color); text-decoration: none; }
  .used a:hover { text-decoration: underline; }
  .used .none { color: var(--warning-color, #ffa600); }
  .add-row { display: flex; gap: 10px; align-items: center; padding: 12px 16px; flex-wrap: wrap; border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .add-row input[type=text] { flex: 1 1 200px; }
  .theme-row { padding: 12px 8px 12px 16px; }
  .theme-row + .theme-row { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .theme-head { display: flex; align-items: center; gap: 10px; }
  .theme-head .grow { flex: 1; min-width: 0; }
  .theme-head .name { display: flex; align-items: center; gap: 8px; }
  .editor { margin: 12px 0 4px; display: grid; gap: 10px; padding-right: 8px; }
  .range { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; font-size: 14px; }
  .range select { padding: 6px 8px; font-size: 14px; }
  .range input[type=time] { font: inherit; font-size: 14px; color: var(--primary-text-color); padding: 5px 6px;
    background: var(--input-fill-color, var(--secondary-background-color, rgba(0,0,0,.04)));
    border: 1px solid var(--divider-color, rgba(0,0,0,.2)); border-radius: 8px; }
  .editor-foot { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; align-items: center; }
  .editor-foot .msg { flex: 1; }
  .tags { display: flex; flex-wrap: wrap; gap: 6px 16px; padding: 4px 0 2px; }
  .tags label { display: flex; align-items: center; gap: 6px; font-size: 14px; }
  .tag-editor { padding: 0 16px 12px 16px; }
  .chip.theme { display: inline-flex; align-items: center; gap: 5px; }
  .chips { display: inline-flex; flex-wrap: wrap; gap: 4px; vertical-align: middle; }
  .filter { font-size: 14px; padding: 6px 8px; }

  @media (max-width: 600px) {
    main { padding: 16px 8px 40px; }
    li { padding-left: 12px; }
    /* Icon-only row buttons on phones, but only when HA's icons are available. */
    :host(.icons) .label { display: none; }
    :host(.icons) button.icon-only-narrow { padding: 0; width: 40px; justify-content: center; }
    :host(:not(.icons)) li { flex-wrap: wrap; }
    :host(:not(.icons)) .actions { width: 100%; justify-content: flex-end; }
  }
`;

class NoticomPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._file = null;
    this._busy = false;
    this._audio = null;
    this._playingKey = null;
    this._tab = "themes";
    this._themes = null;
    this._sounds = null;
    this._soundThemes = [];
    this._filter = "all";
    this._tagging = null;
    this._editing = null; // theme id being edited
    this._draft = null; // {name, schedule} while editing
    this._intercom = null;
    this._poll = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._render();
      this._showTab(this._tab);
    }
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = narrow;
  }

  disconnectedCallback() {
    this._stopPreview();
    clearInterval(this._poll);
    this._poll = null;
  }

  connectedCallback() {
    if (this._hass) this._showTab(this._tab);
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  async _load() {
    try {
      this._setSounds(await this._hass.callWS({ type: "noticom/sounds/list" }));
    } catch (err) {
      this._sounds = [];
      this._toast(`Couldn't load sounds: ${err.message || err}`);
    }
    this._renderList();
  }

  _setSounds(res) {
    this._sounds = res.sounds;
    this._soundThemes = res.themes;
    if (this._filter !== "all" && this._filter !== "unused" && !res.themes.some((t) => t.id === this._filter)) {
      this._filter = "all";
    }
    this._renderUploadThemes();
  }

  _render() {
    this.classList.toggle("icons", Boolean(customElements.get("ha-icon")));
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <h1>Noticom</h1>
      </div>
      <nav class="tabs" role="tablist">
        <button class="tab" role="tab" data-tab="themes" aria-selected="true">Themes</button>
        <button class="tab" role="tab" data-tab="sounds" aria-selected="false">Sounds</button>
        <button class="tab" role="tab" data-tab="intercom" aria-selected="false">Intercom</button>
        <button class="tab" role="tab" data-tab="settings" aria-selected="false">Settings</button>
      </nav>
      <main>
      <section data-panel="themes">
        <div class="section-head"><h2>Themes</h2></div>
        <p class="hint" style="margin:0 4px 16px">
          Automations play <b>chimes</b>, like <i>doorbell</i> or <i>mailbox</i>.
          Each <b>theme</b> picks which sound a chime makes. Anything a theme
          leaves blank plays its Default sound, so a holiday theme only needs the
          chimes you want to change.
        </p>
        <div class="card th-now"><div class="empty">Loading…</div></div>
        <div class="th-warnings"></div>
        <div class="card">
          <div class="list-head"><span>Chimes</span><span class="count th-count"></span></div>
          <div class="th-grid"><div class="empty">Loading…</div></div>
          <div class="add-row">
            <input type="text" class="th-new-chime" maxlength="48" placeholder="New chime, e.g. garbage" autocomplete="off" spellcheck="false" aria-label="New chime name">
            <button class="primary th-add-chime"><ha-icon icon="mdi:plus"></ha-icon>Add chime</button>
          </div>
        </div>
        <div class="card">
          <div class="list-head"><span>Themes and schedule</span></div>
          <p class="hint" style="margin:12px 16px 4px">When dates overlap, the shorter date range wins. If they're the same length, the theme higher in this list wins.</p>
          <div class="th-list"></div>
          <div class="add-row">
            <input type="text" class="th-new-theme" maxlength="40" placeholder="New theme, e.g. Halloween" autocomplete="off" aria-label="New theme name">
            <button class="primary th-add-theme"><ha-icon icon="mdi:plus"></ha-icon>Add theme</button>
          </div>
        </div>
      </section>

      <section data-panel="sounds" hidden>
        <div class="section-head">
          <h2>Sounds</h2>
        </div>
        <p class="hint" style="margin:0 4px 16px">
          Your sound library. Upload WAV or MP3 files; each is evened out in
          loudness and copied to every node ahead of time. Pick which sound
          each chime plays on the Themes tab.
        </p>

        <div class="card upload">
          <div class="drop" tabindex="0" role="button" aria-label="Choose a WAV or MP3 file">
            <ha-icon icon="mdi:upload"></ha-icon>
            <strong class="drop-title">Choose a WAV or MP3 file</strong>
            <span class="hint drop-sub">or drag one here · up to 10 MB</span>
          </div>
          <input type="file" accept="${ACCEPT}" hidden>
          <div class="row">
            <label class="field">Sound name
              <input type="text" class="name-input" maxlength="48" placeholder="e.g. mailbox" autocomplete="off" spellcheck="false">
            </label>
            <button class="primary upload-btn" disabled><ha-icon icon="mdi:check"></ha-icon>Upload</button>
          </div>
          <label class="replace" hidden><input type="checkbox" class="replace-box"> Replace the existing sound with this name</label>
          <label class="replace make-chime-row"><input type="checkbox" class="make-chime" checked> <span class="make-chime-label">Also make a chime with this name that plays it</span></label>
          <div class="up-themes" hidden><div class="hint">File under themes:</div><div class="tags up-tags"></div></div>
          <div class="msg" role="status" aria-live="polite"></div>
        </div>

        <div class="card">
          <div class="list-head"><span>Your sounds <span class="count snd-count"></span></span>
            <select class="filter" aria-label="Show sounds"></select></div>
          <div class="list"><div class="empty">Loading…</div></div>
        </div>
      </section>

      <section data-panel="intercom" hidden>
        <div class="section-head"><h2>Intercom</h2></div>
        <p class="hint" style="margin:0 4px 16px">
          Hold a node's button to talk; release to send. Messages play on the
          nodes it can talk to, after the intercom chime. Automations can react
          to the <code>noticom_message</code> event.
        </p>
        <div class="card pad">
          <div class="setting">
            <div>
              <div class="title">Intercom chime</div>
              <div class="hint">Plays before every message. This sets the <i>intercom</i> chime's Default sound; themes can change it.</div>
            </div>
            <select class="ic-chime" aria-label="Intercom chime"></select>
          </div>
        </div>
        <div class="card">
          <div class="list-head"><span>Who each node can talk to</span></div>
          <div class="ic-nodes"><div class="empty">Loading…</div></div>
        </div>
        <div class="card">
          <div class="list-head"><span>Recent messages</span><span class="count">last 10, up to an hour</span></div>
          <div class="ic-messages"><div class="empty">Loading…</div></div>
        </div>
      </section>

      <section data-panel="settings" hidden>
        <div class="section-head"><h2>Settings</h2></div>
        <div class="card">
          <div class="list-head"><span>Add a node</span></div>
          <p class="hint" style="margin:12px 16px 4px">Run one of these on a fresh Raspberry Pi (over SSH), then add the node under <b>Settings → Devices &amp; services</b>.</p>
          <div class="cmds st-cmds"></div>
        </div>
        <div class="card">
          <div class="list-head"><span>Node software</span><span class="count st-latest"></span></div>
          <div class="st-software"><div class="empty">Loading…</div></div>
          <div class="form-foot" style="padding-top:12px">
            <span class="hint">Nodes also show up under <b>Settings → Updates</b> when a new version is out.</span>
            <button class="primary st-update-all" disabled><ha-icon icon="mdi:update"></ha-icon>Update all</button>
          </div>
        </div>
        <div class="card pad">
          <label class="switch-row">
            <div>
              <div class="title" style="font-size:16px">Chimes jump the queue</div>
              <div class="hint">A chime plays before intercom messages that are still waiting. It never cuts off what's already playing.</div>
            </div>
            <input type="checkbox" class="st-priority">
          </label>
        </div>
        <div class="card">
          <div class="list-head"><span>Defaults for new nodes</span></div>
          <p class="hint" style="margin:12px 16px 0">Nodes you adopt from now on start with these. Nodes you've already adopted keep their own settings; change those on each node's device page.</p>
          <div class="form">
            <label for="d-volume">Volume</label>
            <div class="ctl"><input type="range" id="d-volume" min="0" max="100" step="1"><span class="val" data-for="d-volume"></span></div>
            <label for="d-mic_gain">Mic gain</label>
            <div class="ctl"><input type="range" id="d-mic_gain" min="0" max="100" step="1"><span class="val" data-for="d-mic_gain"></span></div>
            <label for="d-mic_boost">Mic boost</label>
            <div class="ctl"><select id="d-mic_boost">
              <option value="0">Off (0 dB)</option><option value="1">+13 dB</option>
              <option value="2">+20 dB</option><option value="3">+29 dB</option>
            </select></div>
            <label for="d-ptt_enabled">Push to talk</label>
            <div class="ctl"><input type="checkbox" id="d-ptt_enabled"><span class="hint">Button records intercom messages</span></div>
            <label for="d-button_pin">Button GPIO pin</label>
            <div class="ctl"><input type="number" id="d-button_pin" min="0" max="27" step="1"><span class="hint">13: HAT Grove connector · 17: HAT onboard button · 0: no button</span></div>
            <label for="d-button_nc">Button type</label>
            <div class="ctl"><select id="d-button_nc">
              <option value="false">Normally open (most buttons)</option>
              <option value="true">Normally closed</option>
            </select></div>
            <label for="d-intercom_targets">Can talk to</label>
            <div class="ctl"><select id="d-intercom_targets">
              <option value="all">All nodes</option>
              <option value="none">Nobody yet (choose on the Intercom tab)</option>
            </select></div>
          </div>
          <div class="form-foot">
            <span class="msg st-msg" role="status" aria-live="polite"></span>
            <button class="primary st-save"><ha-icon icon="mdi:content-save"></ha-icon>Save defaults</button>
          </div>
        </div>
      </section>
      </main>
    `;

    const root = this.shadowRoot;
    const menu = root.querySelector("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;

    root.querySelectorAll(".tab").forEach((t) =>
      t.addEventListener("click", () => this._showTab(t.dataset.tab))
    );
    root.querySelector(".ic-chime").addEventListener("change", (e) =>
      this._setChime(e.target.value || null)
    );
    root.querySelector(".st-priority").addEventListener("change", (e) =>
      this._saveSettings({ chime_priority: e.target.checked })
    );
    root.querySelector(".st-update-all").addEventListener("click", () => this._updateNodes());
    root.querySelector(".st-save").addEventListener("click", () =>
      this._saveSettings({ node_defaults: this._readDefaults() })
    );
    root.querySelectorAll('.form input[type="range"]').forEach((r) =>
      r.addEventListener("input", () => this._showRange(r))
    );
    root.querySelectorAll(".form input, .form select").forEach((el) =>
      el.addEventListener("change", () => this._settingsMsg(""))
    );

    const drop = root.querySelector(".drop");
    const input = root.querySelector('input[type="file"]');
    drop.addEventListener("click", () => input.click());
    drop.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
    });
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("dragging"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("dragging"));
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      drop.classList.remove("dragging");
      if (e.dataTransfer.files.length) this._pick(e.dataTransfer.files[0]);
    });
    input.addEventListener("change", () => { if (input.files.length) this._pick(input.files[0]); input.value = ""; });
    root.querySelector(".name-input").addEventListener("input", () => this._validate());
    root.querySelector(".replace-box").addEventListener("change", () => this._validate());
    root.querySelector(".upload-btn").addEventListener("click", () => this._upload());
    root.querySelector(".make-chime").addEventListener("change", (e) => { e.target.dataset.touched = "1"; });
    root.querySelector(".filter").addEventListener("change", (e) => { this._filter = e.target.value; this._renderList(); });
    root.querySelector(".th-add-chime").addEventListener("click", () => this._addChime());
    root.querySelector(".th-new-chime").addEventListener("keydown", (e) => { if (e.key === "Enter") this._addChime(); });
    root.querySelector(".th-add-theme").addEventListener("click", () => this._addTheme());
    root.querySelector(".th-new-theme").addEventListener("keydown", (e) => { if (e.key === "Enter") this._addTheme(); });
    root.querySelector(".name-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") this._upload();
    });
  }

  _pick(file) {
    if (!/\.(wav|mp3)$/i.test(file.name)) {
      this._message("Choose a .wav or .mp3 file.", true);
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      this._message("That file is over 10 MB; chimes should be short.", true);
      return;
    }
    this._file = file;
    const root = this.shadowRoot;
    root.querySelector(".drop-title").textContent = file.name;
    root.querySelector(".drop-sub").textContent = `${(file.size / 1024).toFixed(0)} KB · click to choose a different file`;
    const nameInput = root.querySelector(".name-input");
    nameInput.value = suggestName(file.name);
    root.querySelector(".replace-box").checked = false;
    const make = root.querySelector(".make-chime");
    if (!make.dataset.touched) make.checked = !this._chosenUploadThemes().length;
    this._message("");
    this._validate();
    nameInput.focus();
    nameInput.select();
  }

  _existing(name) {
    const key = name.trim().toLowerCase();
    return (this._sounds || []).find((c) => c.name.toLowerCase() === key);
  }

  _chosenUploadThemes() {
    return [...this.shadowRoot.querySelectorAll(".up-tags input:checked")].map((b) => b.value);
  }

  _renderUploadThemes() {
    const root = this.shadowRoot;
    const others = this._soundThemes.filter((t) => t.id !== "default");
    const chosen = new Set(this._chosenUploadThemes());
    root.querySelector(".up-themes").hidden = !others.length;
    root.querySelector(".up-tags").innerHTML = others.map((t) => `
      <label><input type="checkbox" value="${esc(t.id)}" ${chosen.has(t.id) ? "checked" : ""}>
        <span class="swatch" style="background:${this._color(t.id)}"></span>${esc(t.name)}</label>`).join("");
    root.querySelectorAll(".up-tags input").forEach((box) => box.addEventListener("change", () => {
      // Holiday sounds usually aren't chimes of their own.
      const make = root.querySelector(".make-chime");
      if (!make.dataset.touched) make.checked = !this._chosenUploadThemes().length;
    }));
  }

  _color(themeId) {
    if (themeId === "default") return "var(--disabled-color, #9e9e9e)";
    const list = (this._themes ? this._themes.themes : this._soundThemes).filter((t) => t.id !== "default");
    const i = list.findIndex((t) => t.id === themeId);
    return PALETTE[(i < 0 ? 0 : i) % PALETTE.length];
  }

  _validate() {
    const root = this.shadowRoot;
    const name = root.querySelector(".name-input").value.trim();
    const replaceRow = root.querySelector(".replace");
    const exists = name && this._existing(name);
    replaceRow.hidden = !exists;
    const chimeTaken = name && this._themes && this._themes.chimes.some((c) => c.name.toLowerCase() === name.toLowerCase());
    root.querySelector(".make-chime-row").hidden = Boolean(chimeTaken);
    root.querySelector(".make-chime-label").textContent = name
      ? `Also make a chime called “${name}” that plays it`
      : "Also make a chime with this name that plays it";
    let error = "";
    if (name && !NAME_RE.test(name)) {
      error = "Use letters, numbers, spaces, - and _ (start with a letter or number).";
    } else if (exists && !root.querySelector(".replace-box").checked) {
      error = `A sound named “${exists.name}” already exists.`;
    }
    if (this._file) this._message(error, Boolean(error));
    root.querySelector(".upload-btn").disabled = this._busy || !this._file || !name || Boolean(error);
  }

  _message(text, isError = false) {
    const msg = this.shadowRoot.querySelector(".msg");
    msg.textContent = text;
    msg.classList.toggle("error", isError);
  }

  async _upload() {
    const root = this.shadowRoot;
    const btn = root.querySelector(".upload-btn");
    if (btn.disabled) return;
    const name = root.querySelector(".name-input").value.trim();
    const form = new FormData();
    form.append("name", name);
    form.append("replace", root.querySelector(".replace-box").checked ? "true" : "false");
    const makeRow = root.querySelector(".make-chime-row");
    form.append("make_chime", !makeRow.hidden && root.querySelector(".make-chime").checked ? "true" : "false");
    form.append("themes", this._chosenUploadThemes().join(","));
    form.append("file", this._file, this._file.name);
    this._busy = true;
    btn.disabled = true;
    this._message("Uploading and converting…");
    let failure = "";
    try {
      const resp = await this._hass.fetchWithAuth(UPLOAD_URL, { method: "POST", body: form });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(body.error || `Upload failed (${resp.status})`);
      this._sounds = body.sounds;
      this._file = null;
      this._themes = null; // chimes may have changed; reload when shown
      root.querySelector(".drop-title").textContent = "Choose a WAV or MP3 file";
      root.querySelector(".drop-sub").textContent = "or drag one here · up to 10 MB";
      root.querySelector(".name-input").value = "";
      root.querySelector(".replace").hidden = true;
      this._message(body.chime
        ? `Added the sound and the chime “${body.chime}”. Nodes are downloading it now.`
        : `Added “${body.sound}”. Nodes are downloading it now. Pick it for a chime on the Themes tab.`);
      this._renderList();
    } catch (err) {
      failure = err.message || String(err);
    } finally {
      this._busy = false;
      this._validate();
      if (failure) this._message(failure, true); // keep the server's reason visible
    }
  }

  _renderList() {
    const root = this.shadowRoot;
    const list = root.querySelector(".list");
    const all = this._sounds || [];
    const filter = root.querySelector(".filter");
    filter.innerHTML = [
      `<option value="all">All sounds</option>`,
      ...this._soundThemes.map((t) => `<option value="${esc(t.id)}">${esc(t.name)} sounds</option>`),
      `<option value="unused">Not used anywhere</option>`,
    ].join("");
    filter.value = this._filter;
    const sounds = all.filter((c) =>
      this._filter === "all" ? true
      : this._filter === "unused" ? !c.used.length
      : c.themes.includes(this._filter));
    root.querySelector(".snd-count").textContent = all.length ? `(${sounds.length === all.length ? all.length : `${sounds.length} of ${all.length}`})` : "";
    if (!all.length) {
      list.innerHTML = `<div class="empty"><ha-icon icon="mdi:bell-off-outline"></ha-icon>No sounds yet. Upload one above.</div>`;
      return;
    }
    if (!sounds.length) {
      list.innerHTML = `<div class="empty">No sounds here.</div>`;
      return;
    }
    const themeName = (id) => (this._soundThemes.find((t) => t.id === id) || {}).name || id;
    const others = this._soundThemes.filter((t) => t.id !== "default");
    list.innerHTML = `<ul>${sounds
      .map((c) => {
        const used = c.used.length
          ? `Plays for ${c.used.map((u) => `${esc(u.chime)}${u.theme_id === "default" ? "" : ` (${esc(u.theme)})`}`).join(", ")}`
          : "Not used by any chime";
        const chips = c.themes.filter((id) => id !== "default").map((id) =>
          `<span class="chip theme"><span class="swatch" style="background:${this._color(id)}"></span>${esc(themeName(id))}</span>`).join("");
        const tagging = this._tagging === c.name;
        return `
        <li data-name="${esc(c.name)}" data-hash="${esc(c.hash)}" style="flex-wrap:wrap">
          <div class="info">
            <div class="name">${esc(c.name)}</div>
            <div class="meta">${c.duration.toFixed(1)} s · ${used}</div>
            ${chips ? `<div class="recips">${chips}</div>` : ""}
          </div>
          <div class="actions">
            <button class="preview icon-only-narrow" aria-label="Preview ${esc(c.name)} here">
              <ha-icon icon="${this._playingKey === c.hash ? "mdi:stop" : "mdi:play"}"></ha-icon><span class="label">${this._playingKey === c.hash ? "Stop" : "Preview"}</span>
            </button>
            <button class="test icon-only-narrow" aria-label="Play ${esc(c.name)} on all nodes">
              <ha-icon icon="mdi:bullhorn-outline"></ha-icon><span class="label">Play on nodes</span>
            </button>
            ${others.length ? `<button class="tag icon-only-narrow" aria-label="Themes for ${esc(c.name)}" aria-expanded="${tagging}">
              <ha-icon icon="mdi:palette-outline"></ha-icon><span class="label">Themes</span>
            </button>` : ""}
            <button class="danger delete icon-only-narrow" aria-label="Delete ${esc(c.name)}">
              <ha-icon icon="mdi:delete-outline"></ha-icon><span class="label">Delete</span>
            </button>
          </div>
          ${tagging ? `<div class="tag-editor" style="flex-basis:100%;padding-left:0">
            <div class="hint">File this sound under (it's also counted in any theme that uses it):</div>
            <div class="tags">${others.map((t) => {
              const usedHere = c.used.some((u) => u.theme_id === t.id);
              return `<label ${usedHere ? `title="It plays for a chime in ${esc(t.name)}"` : ""}><input type="checkbox" value="${esc(t.id)}"
                ${c.themes.includes(t.id) ? "checked" : ""} ${usedHere ? "disabled data-used" : ""}>
              <span class="swatch" style="background:${this._color(t.id)}"></span>${esc(t.name)}${usedHere ? ` <span class="hint">(in use)</span>` : ""}</label>`;
            }).join("")}</div>
          </div>` : ""}
        </li>`;
      })
      .join("")}</ul>`;
    list.querySelectorAll("li").forEach((li) => {
      const { name, hash } = li.dataset;
      li.querySelector(".preview").addEventListener("click", () => this._preview(hash, PREVIEW_URL(hash)));
      li.querySelector(".test").addEventListener("click", () => this._playOnNodes({ sound: name }));
      li.querySelector(".tag")?.addEventListener("click", () => {
        this._tagging = this._tagging === name ? null : name;
        this._renderList();
      });
      li.querySelectorAll(".tag-editor input").forEach((box) => box.addEventListener("change", () => {
        const chosen = [...li.querySelectorAll(".tag-editor input:checked:not([data-used])")].map((b) => b.value);
        this._tagSound(name, chosen);
      }));
      li.querySelector(".delete").addEventListener("click", () => this._delete(name));
    });
  }

  async _tagSound(name, themes) {
    try {
      this._setSounds(await this._hass.callWS({ type: "noticom/sounds/tag", name, themes }));
      this._themes = null;
      this._renderList();
    } catch (err) {
      this._toast(`Couldn't save: ${err.message || err}`);
      this._load();
    }
  }

  _stopPreview() {
    if (this._audio) {
      this._audio.pause();
      URL.revokeObjectURL(this._audio.src);
      this._audio = null;
    }
    this._playingKey = null;
  }

  _rerenderPlayback() {
    if (this._tab === "sounds") this._renderList();
    if (this._tab === "themes" && this._themes) this._renderGrid();
    if (this._intercom) this._renderMessages();
  }

  async _preview(key, url) {
    const wasPlaying = this._playingKey === key;
    this._stopPreview();
    if (wasPlaying) { this._rerenderPlayback(); return; }
    try {
      const resp = await this._hass.fetchWithAuth(url);
      if (resp.status === 404) throw new Error("it's no longer available");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const audio = new Audio(URL.createObjectURL(await resp.blob()));
      audio.addEventListener("ended", () => { this._stopPreview(); this._rerenderPlayback(); });
      this._audio = audio;
      this._playingKey = key;
      this._rerenderPlayback();
      await audio.play();
    } catch (err) {
      this._stopPreview();
      this._rerenderPlayback();
      this._toast(`Couldn't play: ${err.message || err}`);
    }
  }

  /* ---------- Themes tab ---------- */

  async _loadThemes(quiet = false) {
    try {
      this._themes = await this._hass.callWS({ type: "noticom/themes/get" });
    } catch (err) {
      if (!quiet) this._toast(`Couldn't load themes: ${err.message || err}`);
      return;
    }
    this._renderThemes();
  }

  async _themeWS(msg, done) {
    try {
      this._themes = await this._hass.callWS(msg);
      this._sounds = null; // usage changed; Sounds tab reloads when shown
      if (done) done();
      this._renderThemes();
      return true;
    } catch (err) {
      this._toast(err.message || String(err));
      return false;
    }
  }

  _navigate(path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  _usageLinks(list) {
    return list.map((u) => u.edit
      ? `<a href="${esc(u.edit)}" data-nav="${esc(u.edit)}">${esc(u.name)}</a>`
      : esc(u.name)).join(", ");
  }

  _bindNav(el) {
    el.querySelectorAll("a[data-nav]").forEach((a) => a.addEventListener("click", (e) => {
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
      e.preventDefault();
      this._navigate(a.dataset.nav);
    }));
  }

  _renderThemes() {
    if (!this._themes) return;
    this._renderNow();
    this._renderWarnings();
    this._renderGrid();
    this._renderThemeList();
    if (this._file) this._validate();
  }

  _renderNow() {
    const th = this._themes;
    const el = this.shadowRoot.querySelector(".th-now");
    const a = th.active;
    const why = a.reason === "manual" ? "Chosen by hand"
      : a.reason === "schedule" ? `Scheduled ${esc(fmtRange(a.range))}`
      : "No theme is scheduled right now";
    const now = new Date();
    const doy = (m, d) => { // day of year in a leap year, 1-based
      let n = d;
      for (let i = 0; i < m - 1; i++) n += MONTH_DAYS[i];
      return n;
    };
    const today = doy(now.getMonth() + 1, now.getDate());
    const scheduled = th.themes.filter((t) => !t.default && t.schedule.length);
    el.innerHTML = `
      <div class="now">
        <div>
          <div class="hint">Playing now</div>
          <div class="now-title"><span class="swatch" style="background:${this._color(a.id)}"></span>${esc(a.name)}</div>
          <div class="hint">${why}</div>
        </div>
        <label class="hint" style="display:grid;gap:4px">Theme
          <select class="th-mode">
            <option value="auto">Automatic (follow the schedule)</option>
            ${th.themes.map((t) => `<option value="${esc(t.id)}">${esc(t.name)} only</option>`).join("")}
          </select>
        </label>
      </div>
      <div class="year">
        <div class="strip" role="img" aria-label="Which theme plays on each day of the year">
          ${th.calendar.map((r) => `<span style="width:${(r.days / 366) * 100}%;background:${this._color(r.theme_id)};${r.theme_id === "default" ? "opacity:.35" : ""}"
             title="${esc((th.themes.find((t) => t.id === r.theme_id) || {}).name || "")}: ${esc(r.start === r.end ? fmtDay(r.start) : `${fmtDay(r.start)} – ${fmtDay(r.end)}`)}"></span>`).join("")}
          <span class="today" style="left:calc(${((today - 0.5) / 366) * 100}% - 1px)" title="Today"></span>
        </div>
        <div class="months">${MONTHS.map((m) => `<span>${m}</span>`).join("")}</div>
        ${scheduled.length ? `<div class="legend">${scheduled.map((t) =>
          `<span><span class="swatch" style="background:${this._color(t.id)}"></span>${esc(t.name)}</span>`).join("")}
          <span><span class="swatch" style="background:${this._color("default")};opacity:.35"></span>Default</span></div>`
        : `<div class="hint" style="margin-top:8px">Add a theme below and give it dates to see it here.</div>`}
      </div>`;
    const mode = el.querySelector(".th-mode");
    mode.value = th.mode;
    mode.addEventListener("change", () =>
      this._themeWS({ type: "noticom/themes/set_mode", mode: mode.value }, () =>
        this._toast(mode.value === "auto" ? "Following the schedule" : "Theme changed")));
  }

  _renderWarnings() {
    const th = this._themes;
    const el = this.shadowRoot.querySelector(".th-warnings");
    const boxes = [];
    if (th.missing.length) {
      boxes.push(`<div class="warnbox"><div class="title">No Default sound</div>
        <div class="hint">${th.missing.map((c) => `<b>${esc(c)}</b>`).join(", ")} ${th.missing.length > 1 ? "have" : "has"} no sound in the Default theme, so ${th.missing.length > 1 ? "they play" : "it plays"} nothing when no other theme sets one. Pick a sound below.</div></div>`);
    }
    for (const u of th.unknown) {
      boxes.push(`<div class="warnbox"><div class="title">Unknown chime</div>
        <div class="hint used" style="font-size:14px">${this._usageLinks([u])} plays “${esc(u.chime)}”, but there's no chime with that name. Fix the ${u.kind}, or add the chime below.</div></div>`);
    }
    const info = [];
    if (th.dynamic.length) {
      info.push(`${this._usageLinks(th.dynamic)} ${th.dynamic.length > 1 ? "pick their" : "picks its"} chime with a template, so ${th.dynamic.length > 1 ? "they" : "it"} can't be listed under a chime.`);
    }
    if (th.direct.length) {
      info.push(`${th.direct.map((u) => `${this._usageLinks([u])} plays the sound “${esc(u.sound)}” directly`).join("; ")}, so themes don't change ${th.direct.length > 1 ? "them" : "it"}.`);
    }
    if (info.length) {
      boxes.push(`<div class="warnbox" style="border-left-color:var(--info-color, #039be5)"><div class="used" style="font-size:14px">${info.join("<br>")}</div></div>`);
    }
    el.innerHTML = boxes.length ? `<div class="card">${boxes.join("")}</div>` : "";
    this._bindNav(el);
  }

  _soundOptions(theme, chime) {
    const th = this._themes;
    const picked = chime.sounds[theme.id] || "";
    const opt = (n) => `<option value="${esc(n.name)}" ${n.name === picked ? "selected" : ""}>${esc(n.name)}</option>`;
    if (theme.default) {
      return `<option value="" ${picked ? "" : "selected"}>${chime.builtin ? "No sound" : "No sound (pick one)"}</option>` +
        th.sounds.map(opt).join("");
    }
    const mine = th.sounds.filter((n) => n.themes.includes(theme.id));
    const rest = th.sounds.filter((n) => !n.themes.includes(theme.id));
    const fallback = chime.sounds.default;
    return `<option value="" ${picked ? "" : "selected"}>Default (${esc(fallback || "no sound")})</option>` +
      (mine.length
        ? `<optgroup label="${esc(theme.name)} sounds">${mine.map(opt).join("")}</optgroup><optgroup label="Other sounds">${rest.map(opt).join("")}</optgroup>`
        : rest.map(opt).join(""));
  }

  _renderGrid() {
    const th = this._themes;
    const root = this.shadowRoot;
    const el = root.querySelector(".th-grid");
    root.querySelector(".th-count").textContent = `${th.chimes.length} chime${th.chimes.length === 1 ? "" : "s"}`;
    const hashOf = (name) => (th.sounds.find((n) => n.name === name) || {}).hash;
    el.innerHTML = `<div class="grid-wrap"><table class="grid">
      <thead><tr><th scope="col">Chime</th>${th.themes.map((t) => `
        <th scope="col" class="${t.id === th.active.id ? "on" : ""}"><span class="swatch" style="background:${this._color(t.id)}"></span> ${esc(t.name)}${t.id === th.active.id ? " · now" : ""}</th>`).join("")}</tr></thead>
      <tbody>${th.chimes.map((c) => {
        const users = c.used_by.length
          ? `Used by ${this._usageLinks(c.used_by)}`
          : `<span class="none">Not used by any automation yet</span>`;
        return `<tr data-chime="${esc(c.name)}">
          <th scope="row">
            <div class="chime-name">${esc(c.name)}
              <button class="mini play-chime" title="Play on all nodes (current theme)" aria-label="Play ${esc(c.name)} on all nodes"><ha-icon icon="mdi:bullhorn-outline"></ha-icon></button>
              ${c.builtin ? "" : `<button class="mini danger del-chime" title="Delete chime" aria-label="Delete chime ${esc(c.name)}"><ha-icon icon="mdi:delete-outline"></ha-icon></button>`}
            </div>
            <div class="used">${users}</div>
          </th>
          ${th.themes.map((t) => {
            const effective = c.sounds[t.id] || c.sounds.default;
            const hash = effective && hashOf(effective);
            const playing = hash && this._playingKey === hash;
            return `<td class="${t.id === th.active.id ? "on" : ""}"><div class="cell">
              <select data-theme="${esc(t.id)}" class="${!t.default && !c.sounds[t.id] ? "inherit" : ""}" aria-label="${esc(c.name)} in ${esc(t.name)}">${this._soundOptions(t, c)}</select>
              <button class="mini preview-cell" data-hash="${esc(hash || "")}" ${hash ? "" : "disabled"} aria-label="Preview"><ha-icon icon="${playing ? "mdi:stop" : "mdi:play"}"></ha-icon></button>
            </div></td>`;
          }).join("")}
        </tr>`;
      }).join("")}</tbody></table></div>`;
    this._bindNav(el);
    el.querySelectorAll("tr[data-chime]").forEach((tr) => {
      const chime = tr.dataset.chime;
      tr.querySelector(".play-chime").addEventListener("click", () => this._playOnNodes({ chime }));
      tr.querySelector(".del-chime")?.addEventListener("click", () => this._deleteChime(chime));
      tr.querySelectorAll("select").forEach((sel) => sel.addEventListener("change", () =>
        this._themeWS({ type: "noticom/themes/set_sound", theme_id: sel.dataset.theme, chime, sound: sel.value || null })));
      tr.querySelectorAll(".preview-cell").forEach((b) => b.addEventListener("click", () => {
        if (b.dataset.hash) this._preview(b.dataset.hash, PREVIEW_URL(b.dataset.hash));
      }));
    });
  }

  _renderThemeList() {
    const th = this._themes;
    const el = this.shadowRoot.querySelector(".th-list");
    const others = th.themes.filter((t) => !t.default);
    const def = th.themes.find((t) => t.default);
    const rows = others.map((t, i) => {
      const editing = this._editing === t.id;
      const when = t.schedule.length ? t.schedule.map(fmtRange).join(" · ") : "No dates: plays only when chosen by hand";
      return `<div class="theme-row" data-theme="${esc(t.id)}">
        <div class="theme-head">
          <span class="swatch" style="background:${this._color(t.id)}"></span>
          <div class="grow">
            <div class="name">${esc(t.name)}${t.id === th.active.id ? ` <span class="badge">Playing now</span>` : ""}</div>
            <div class="meta">${esc(when)}</div>
          </div>
          <div class="actions">
            <button class="mini th-up" ${i === 0 ? "disabled" : ""} aria-label="Move ${esc(t.name)} up" title="Higher priority"><ha-icon icon="mdi:arrow-up"></ha-icon></button>
            <button class="mini th-down" ${i === others.length - 1 ? "disabled" : ""} aria-label="Move ${esc(t.name)} down" title="Lower priority"><ha-icon icon="mdi:arrow-down"></ha-icon></button>
            <button class="th-edit icon-only-narrow" aria-expanded="${editing}"><ha-icon icon="mdi:calendar-edit"></ha-icon><span class="label">${editing ? "Close" : "Edit"}</span></button>
            <button class="danger th-del icon-only-narrow" aria-label="Delete ${esc(t.name)}"><ha-icon icon="mdi:delete-outline"></ha-icon><span class="label">Delete</span></button>
          </div>
        </div>
        ${editing ? this._editorHTML() : ""}
      </div>`;
    });
    rows.push(`<div class="theme-row"><div class="theme-head">
        <span class="swatch" style="background:${this._color("default")}"></span>
        <div class="grow"><div class="name">${esc(def.name)}${def.id === th.active.id ? ` <span class="badge">Playing now</span>` : ""}</div>
        <div class="meta">Plays whenever no other theme does, and fills in anything a theme leaves blank.</div></div>
      </div></div>`);
    if (!others.length) {
      rows.unshift(`<div class="hint" style="padding:8px 16px">No themes yet. Add one below, for example <i>Halloween</i>, then pick its sounds in the table above and give it dates.</div>`);
    }
    el.innerHTML = rows.join("");
    el.querySelectorAll(".theme-row[data-theme]").forEach((row) => {
      const id = row.dataset.theme;
      const order = others.map((t) => t.id);
      const move = (delta) => {
        const i = order.indexOf(id);
        order.splice(i, 1);
        order.splice(i + delta, 0, id);
        this._themeWS({ type: "noticom/themes/reorder", order });
      };
      row.querySelector(".th-up").addEventListener("click", () => move(-1));
      row.querySelector(".th-down").addEventListener("click", () => move(1));
      row.querySelector(".th-edit").addEventListener("click", () => {
        if (this._editing === id) { this._editing = null; this._draft = null; }
        else {
          const t = others.find((x) => x.id === id);
          this._editing = id;
          this._draft = { name: t.name, schedule: t.schedule.map((r) => ({ ...r, hours: Boolean(r.from) })) };
        }
        this._renderThemeList();
      });
      row.querySelector(".th-del").addEventListener("click", () => this._deleteTheme(id));
      if (this._editing === id) this._bindEditor(row);
    });
  }

  _editorHTML() {
    const d = this._draft;
    const monthSel = (cls, i, mmdd) => {
      const m = Number(mmdd.split("-")[0]);
      return `<select class="${cls}-m" data-i="${i}" aria-label="Month">${MONTHS.map((n, k) =>
        `<option value="${k + 1}" ${k + 1 === m ? "selected" : ""}>${n}</option>`).join("")}</select>`;
    };
    const daySel = (cls, i, mmdd) => {
      const [m, day] = mmdd.split("-").map(Number);
      return `<select class="${cls}-d" data-i="${i}" aria-label="Day">${Array.from({ length: MONTH_DAYS[m - 1] }, (_, k) =>
        `<option value="${k + 1}" ${k + 1 === day ? "selected" : ""}>${k + 1}</option>`).join("")}</select>`;
    };
    return `<div class="editor">
      <label class="field" style="max-width:340px">Name
        <input type="text" class="ed-name" maxlength="40" value="${esc(d.name)}">
      </label>
      <div class="hint">Dates (every year):</div>
      ${d.schedule.length ? d.schedule.map((r, i) => `
        <div class="range">
          ${monthSel("ed-start", i, r.start)} ${daySel("ed-start", i, r.start)}
          <span>to</span>
          ${monthSel("ed-end", i, r.end)} ${daySel("ed-end", i, r.end)}
          <label style="display:flex;align-items:center;gap:6px"><input type="checkbox" class="ed-hours" data-i="${i}" ${r.hours ? "checked" : ""}>only between</label>
          ${r.hours ? `<input type="time" class="ed-from" data-i="${i}" value="${esc(r.from || "17:00")}" aria-label="From">
            <span>and</span>
            <input type="time" class="ed-to" data-i="${i}" value="${esc(r.to || "23:00")}" aria-label="Until">` : ""}
          <button class="mini danger ed-remove" data-i="${i}" aria-label="Remove these dates"><ha-icon icon="mdi:close"></ha-icon></button>
        </div>`).join("") : `<div class="hint">No dates yet: this theme only plays when you choose it by hand.</div>`}
      <div><button class="ed-add"><ha-icon icon="mdi:calendar-plus"></ha-icon>Add dates</button></div>
      <div class="editor-foot">
        <span class="msg ed-msg" role="status"></span>
        <button class="ed-cancel">Cancel</button>
        <button class="primary ed-save"><ha-icon icon="mdi:content-save"></ha-icon>Save</button>
      </div>
    </div>`;
  }

  _bindEditor(row) {
    const d = this._draft;
    const pad = (n) => String(n).padStart(2, "0");
    const read = (cls, i) => {
      const m = Number(row.querySelector(`.${cls}-m[data-i="${i}"]`).value);
      const day = Math.min(Number(row.querySelector(`.${cls}-d[data-i="${i}"]`).value), MONTH_DAYS[m - 1]);
      return `${pad(m)}-${pad(day)}`;
    };
    row.querySelector(".ed-name").addEventListener("input", (e) => { d.name = e.target.value; });
    row.querySelectorAll(".range select").forEach((sel) => sel.addEventListener("change", () => {
      const i = Number(sel.dataset.i);
      const before = d.schedule[i].start;
      d.schedule[i].start = read("ed-start", i);
      d.schedule[i].end = sel.className.startsWith("ed-start") && d.schedule[i].end === before
        ? d.schedule[i].start // moving a one-day range keeps it one day
        : read("ed-end", i);
      if (sel.className.endsWith("-m")) this._renderThemeList(); // day list depends on the month
    }));
    row.querySelectorAll(".ed-hours").forEach((box) => box.addEventListener("change", () => {
      const r = d.schedule[Number(box.dataset.i)];
      r.hours = box.checked;
      if (r.hours) { r.from = r.from || "17:00"; r.to = r.to || "23:00"; }
      this._renderThemeList();
    }));
    row.querySelectorAll(".ed-from, .ed-to").forEach((inp) => inp.addEventListener("change", () => {
      d.schedule[Number(inp.dataset.i)][inp.classList.contains("ed-from") ? "from" : "to"] = inp.value;
    }));
    row.querySelectorAll(".ed-remove").forEach((b) => b.addEventListener("click", () => {
      d.schedule.splice(Number(b.dataset.i), 1);
      this._renderThemeList();
    }));
    row.querySelector(".ed-add").addEventListener("click", () => {
      const now = new Date();
      const today = `${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
      d.schedule.push({ start: today, end: today, from: null, to: null, hours: false });
      this._renderThemeList();
    });
    row.querySelector(".ed-cancel").addEventListener("click", () => {
      this._editing = null; this._draft = null; this._renderThemeList();
    });
    row.querySelector(".ed-save").addEventListener("click", async () => {
      const schedule = d.schedule.map((r) => ({
        start: r.start, end: r.end, from: r.hours ? r.from : null, to: r.hours ? r.to : null,
      }));
      const id = this._editing;
      const ok = await this._themeWS(
        { type: "noticom/themes/update", theme_id: id, name: d.name, schedule },
        () => { this._editing = null; this._draft = null; });
      if (ok) this._toast("Theme saved");
    });
  }

  async _addChime() {
    const input = this.shadowRoot.querySelector(".th-new-chime");
    const name = input.value.trim();
    if (!name) { input.focus(); return; }
    if (!NAME_RE.test(name)) {
      this._toast("Chime names can use letters, numbers, spaces, - and _ (start with a letter or number).");
      return;
    }
    // A sound with the same name becomes its Default sound.
    const same = this._themes.sounds.find((n) => n.name.toLowerCase() === name.toLowerCase());
    await this._themeWS({ type: "noticom/themes/add_chime", name, sound: same ? same.name : null }, () => {
      input.value = "";
      this._toast(same ? `Added “${name}”, playing the sound “${same.name}”` : `Added “${name}”. Pick its Default sound in the table.`);
    });
  }

  async _deleteChime(name) {
    const c = this._themes.chimes.find((x) => x.name === name);
    const users = c && c.used_by.length ? `\n\nStill used by: ${c.used_by.map((u) => u.name).join(", ")}. Those will fail until you change them.` : "";
    if (!confirm(`Delete the chime “${name}” from every theme? Its sounds stay in the library.${users}`)) return;
    await this._themeWS({ type: "noticom/themes/delete_chime", name });
  }

  async _addTheme() {
    const input = this.shadowRoot.querySelector(".th-new-theme");
    const name = input.value.trim();
    if (!name) { input.focus(); return; }
    await this._themeWS({ type: "noticom/themes/add", name }, () => {
      input.value = "";
      const added = this._themes.themes.find((t) => t.name === name);
      if (added) {
        this._editing = added.id;
        this._draft = { name: added.name, schedule: [] };
      }
      this._toast(`Added “${name}”. Pick its sounds in the table, and add dates.`);
    });
  }

  async _deleteTheme(id) {
    const t = this._themes.themes.find((x) => x.id === id);
    if (!confirm(`Delete the theme “${t.name}”? Its sounds stay in the library.`)) return;
    await this._themeWS({ type: "noticom/themes/delete", theme_id: id }, () => {
      if (this._editing === id) { this._editing = null; this._draft = null; }
    });
  }

  /* ---------- Intercom tab ---------- */

  _showTab(tab) {
    this._tab = tab;
    const root = this.shadowRoot;
    root.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === tab)));
    root.querySelectorAll("section[data-panel]").forEach((sec) => { sec.hidden = sec.dataset.panel !== tab; });
    clearInterval(this._poll);
    this._poll = null;
    if (tab === "intercom") {
      this._loadIntercom();
      this._poll = setInterval(() => this._loadIntercom(), 10000);
    } else if (tab === "settings") {
      this._loadSettings();
    } else if (tab === "themes") {
      this._loadThemes();
      this._poll = setInterval(() => { if (!this._editing) this._loadThemes(); }, 60000);
    } else {
      this._load();
      if (!this._themes) this._loadThemes(true);
    }
  }

  async _loadIntercom() {
    try {
      this._intercom = await this._hass.callWS({ type: "noticom/intercom/get" });
    } catch (err) {
      this._toast(`Couldn't load intercom settings: ${err.message || err}`);
      return;
    }
    this._renderIntercom();
  }

  _renderIntercom() {
    const ic = this._intercom;
    const root = this.shadowRoot;
    const select = root.querySelector(".ic-chime");
    if (document.activeElement !== this || this.shadowRoot.activeElement !== select) {
      select.innerHTML =
        `<option value="">No chime</option>` +
        ic.chimes.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
      select.value = ic.chime || "";
    }

    const nodesEl = root.querySelector(".ic-nodes");
    if (!ic.nodes.length) {
      nodesEl.innerHTML = `<div class="empty">No nodes yet. Adopt a node to use the intercom.</div>`;
    } else {
      nodesEl.innerHTML = ic.nodes.map((n) => {
        const others = ic.nodes.filter((o) => o.node_id !== n.node_id);
        const all = n.targets === "all";
        const picks = all ? [] : n.targets;
        return `
          <div class="node" data-node="${esc(n.node_id)}">
            <div class="node-head">
              <div class="node-name">
                <span class="dot ${n.connected ? "on" : ""}" title="${n.connected ? "Online" : "Offline"}"></span>
                <span>${esc(n.name)}</span>
                ${!n.can_talk
                  ? `<span class="badge">Chime only</span>`
                  : n.ptt_enabled ? "" : `<span class="badge">Push to talk off</span>`}
              </div>
              ${n.can_talk ? `<select class="ic-mode" aria-label="Who ${esc(n.name)} can talk to" ${others.length ? "" : "disabled"}>
                <option value="all" ${all ? "selected" : ""}>All nodes</option>
                <option value="some" ${all ? "" : "selected"}>Only selected nodes</option>
              </select>` : ""}
            </div>
            ${!n.can_talk
              ? `<div class="hint" style="margin-top:6px">No microphone or button, so it plays chimes and messages but can't send them.</div>`
              : !others.length
              ? `<div class="hint" style="margin-top:6px">Add another node to send messages to.</div>`
              : all
                ? ""
                : `<div class="picks">${others.map((o) => `
                    <label><input type="checkbox" value="${esc(o.node_id)}" ${picks.includes(o.node_id) ? "checked" : ""}> ${esc(o.name)}</label>`).join("")}
                   ${picks.length ? "" : `<span class="hint">Nobody yet: this node's messages won't play anywhere.</span>`}
                  </div>`}
          </div>`;
      }).join("");
      nodesEl.querySelectorAll(".node").forEach((el) => {
        const nodeId = el.dataset.node;
        el.querySelector(".ic-mode")?.addEventListener("change", (e) => {
          const node = this._intercom.nodes.find((x) => x.node_id === nodeId);
          const current = node.targets === "all" ? [] : node.targets;
          this._setTargets(nodeId, e.target.value === "all" ? "all" : current);
        });
        el.querySelectorAll(".picks input").forEach((box) =>
          box.addEventListener("change", () => {
            const chosen = [...el.querySelectorAll(".picks input:checked")].map((b) => b.value);
            this._setTargets(nodeId, chosen);
          })
        );
      });
    }
    this._renderMessages();
  }

  _renderMessages() {
    const el = this.shadowRoot.querySelector(".ic-messages");
    const msgs = this._intercom.messages;
    if (!msgs.length) {
      el.innerHTML = `<div class="empty"><ha-icon icon="mdi:message-off-outline"></ha-icon>No messages yet. Hold a node's button to record one.</div>`;
      return;
    }
    el.innerHTML = `<ul>${msgs.map((m) => {
      const key = `clip:${m.id}`;
      const playing = this._playingKey === key;
      return `
        <li data-id="${esc(m.id)}">
          <div class="info">
            <div class="name">From ${esc(m.sender)}</div>
            <div class="meta">${ago(m.created)} · ${m.duration.toFixed(1)} s</div>
            <div class="recips">${m.recipients.length
              ? m.recipients.map((r) => `<span class="chip ${esc(r.status)}">${esc(r.name)}: ${STATUS[r.status] || esc(r.status)}</span>`).join("")
              : `<span class="chip">Sent to nobody</span>`}</div>
          </div>
          <div class="actions">
            <button class="play icon-only-narrow" aria-label="${playing ? "Stop" : "Play"} message from ${esc(m.sender)}">
              <ha-icon icon="${playing ? "mdi:stop" : "mdi:play"}"></ha-icon><span class="label">${playing ? "Stop" : "Play"}</span>
            </button>
          </div>
        </li>`;
    }).join("")}</ul>`;
    el.querySelectorAll("li").forEach((li) =>
      li.querySelector(".play").addEventListener("click", () =>
        this._preview(`clip:${li.dataset.id}`, CLIP_URL(li.dataset.id))
      )
    );
  }

  async _setChime(name) {
    try {
      this._intercom = await this._hass.callWS({ type: "noticom/intercom/set_chime", chime: name });
      this._renderIntercom();
      this._toast(name ? `Intercom chime: ${name}` : "Messages will play without a chime");
    } catch (err) {
      this._toast(`Couldn't change the chime: ${err.message || err}`);
      this._loadIntercom();
    }
  }

  async _setTargets(nodeId, targets) {
    try {
      this._intercom = await this._hass.callWS({ type: "noticom/intercom/set_targets", node_id: nodeId, targets });
      this._renderIntercom();
    } catch (err) {
      this._toast(`Couldn't save: ${err.message || err}`);
      this._loadIntercom();
    }
  }

  /* ---------- Settings tab ---------- */

  _showRange(r) {
    this.shadowRoot.querySelector(`.val[data-for="${r.id}"]`).textContent = `${r.value}%`;
  }

  _settingsMsg(text, isError = false) {
    const m = this.shadowRoot.querySelector(".st-msg");
    m.textContent = text;
    m.classList.toggle("error", isError);
  }

  async _loadSettings() {
    try {
      this._applySettings(await this._hass.callWS({ type: "noticom/settings/get" }));
    } catch (err) {
      this._toast(`Couldn't load settings: ${err.message || err}`);
    }
  }

  async _copy(text, button) {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);  // needs https or localhost
      ok = true;
    } catch (_err) {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.cssText = "position:fixed;top:0;left:0;opacity:0";
      this.shadowRoot.appendChild(area);
      area.select();
      try { ok = document.execCommand("copy"); } catch (_e) { ok = false; }
      area.remove();
    }
    if (ok) {
      const label = button.querySelector(".label");
      const old = label.textContent;
      label.textContent = "Copied";
      setTimeout(() => { label.textContent = old; }, 1500);
    } else {
      this._toast("Couldn't copy automatically: select the command and copy it.");
    }
  }

  _renderCommands(cmds) {
    const el = this.shadowRoot.querySelector(".st-cmds");
    const rows = [
      ["Node with a button", cmds.install],
      ["Node without a button (chime-only)", cmds.install_no_button],
      ["Then, to confirm adding a node without pressing its button", cmds.pair],
    ];
    el.innerHTML = rows.map(([label, cmd]) => `
      <div>
        <div class="cmd-label">${esc(label)}</div>
        <div class="cmd"><code>${esc(cmd)}</code>
          <button class="copy" data-cmd="${esc(cmd)}" aria-label="Copy: ${esc(label)}"><ha-icon icon="mdi:content-copy"></ha-icon><span class="label">Copy</span></button>
        </div>
      </div>`).join("");
    el.querySelectorAll(".copy").forEach((b) => b.addEventListener("click", () => this._copy(b.dataset.cmd, b)));
  }

  _renderSoftware(sw) {
    const root = this.shadowRoot;
    root.querySelector(".st-latest").textContent = sw.latest ? `Newest: ${sw.latest}` : "";
    const el = root.querySelector(".st-software");
    if (!sw.nodes.length) {
      el.innerHTML = `<div class="empty">No nodes yet.</div>`;
    } else {
      el.innerHTML = sw.nodes.map((n) => {
        let status;
        if (n.updating) status = `<span class="warn">Updating…</span>`;
        else if (!n.version) status = `<span class="hint">Version unknown</span>`;
        else if (n.update_available && !n.remote_update) status = `<span class="warn">Update available: run the install command on it once over SSH</span>`;
        else if (n.update_available) status = `<span class="warn">Update available</span>`;
        else status = `<span class="ok">Up to date</span>`;
        const canUpdate = n.update_available && n.remote_update && n.connected && !n.updating;
        return `
          <div class="sw-row" data-node="${esc(n.node_id)}">
            <span class="dot ${n.connected ? "on" : ""}" title="${n.connected ? "Online" : "Offline"}"></span>
            <div class="grow">
              <div class="name">${esc(n.name)}</div>
              <div class="meta">${n.version ? esc(n.version) : "–"} · ${status}${n.update_available && !n.connected ? " · offline" : ""}</div>
            </div>
            ${canUpdate ? `<button class="sw-update"><ha-icon icon="mdi:download"></ha-icon><span class="label">Update</span></button>` : ""}
          </div>`;
      }).join("");
      el.querySelectorAll(".sw-update").forEach((b) =>
        b.addEventListener("click", () => this._updateNodes([b.closest(".sw-row").dataset.node]))
      );
    }
    const outdated = sw.nodes.filter((n) => n.update_available && n.remote_update && n.connected && !n.updating);
    const all = root.querySelector(".st-update-all");
    all.disabled = !outdated.length;
    all.lastChild.textContent = outdated.length > 1 ? `Update all (${outdated.length})` : "Update all";
  }

  async _updateNodes(nodeIds) {
    try {
      const res = await this._hass.callWS({ type: "noticom/nodes/update", ...(nodeIds ? { node_ids: nodeIds } : {}) });
      this._renderSoftware(res.software);
      if (res.started.length) this._toast(`Updating ${res.started.join(", ")}. This can take a few minutes.`);
      if (res.skipped.length) this._toast(`Not updated (offline, or needs one update over SSH): ${res.skipped.join(", ")}`);
      clearInterval(this._poll);
      this._poll = setInterval(() => this._loadSettings(), 10000);
    } catch (err) {
      this._toast(`Couldn't start the update: ${err.message || err}`);
    }
  }

  _applySettings(st) {
    const root = this.shadowRoot;
    if (st.commands) this._renderCommands(st.commands);
    if (st.software) this._renderSoftware(st.software);
    root.querySelector(".st-priority").checked = st.chime_priority;
    const d = st.node_defaults;
    const set = (id, v) => { root.getElementById(`d-${id}`).value = String(v); };
    set("volume", d.volume);
    set("mic_gain", d.mic_gain);
    set("mic_boost", d.mic_boost);
    set("button_pin", d.button_pin);
    set("button_nc", d.button_nc);
    set("intercom_targets", d.intercom_targets === "all" ? "all" : "none");
    root.getElementById("d-ptt_enabled").checked = d.ptt_enabled;
    root.querySelectorAll('.form input[type="range"]').forEach((r) => this._showRange(r));
  }

  _readDefaults() {
    const root = this.shadowRoot;
    const v = (id) => root.getElementById(`d-${id}`).value;
    return {
      volume: Number(v("volume")),
      mic_gain: Number(v("mic_gain")),
      mic_boost: Number(v("mic_boost")),
      ptt_enabled: root.getElementById("d-ptt_enabled").checked,
      button_pin: Number(v("button_pin")),
      button_nc: v("button_nc") === "true",
      intercom_targets: v("intercom_targets") === "all" ? "all" : [],
    };
  }

  async _saveSettings(change) {
    if (change.node_defaults) {
      const pin = change.node_defaults.button_pin;
      if (!Number.isInteger(pin) || pin < 0 || pin > 27) {
        this._settingsMsg("Button GPIO pin must be a whole number from 0 (no button) to 27.", true);
        return;
      }
    }
    try {
      this._applySettings(await this._hass.callWS({ type: "noticom/settings/set", ...change }));
      if (change.node_defaults) this._settingsMsg("Saved. New nodes will start with these settings.");
      else this._toast(change.chime_priority ? "Chimes will jump the queue" : "Chimes will wait their turn");
    } catch (err) {
      if (change.node_defaults) this._settingsMsg(`Couldn't save: ${err.message || err}`, true);
      else this._toast(`Couldn't save: ${err.message || err}`);
      this._loadSettings();
    }
  }

  async _playOnNodes(what) {
    try {
      const res = await this._hass.callWS({
        type: "call_service",
        domain: "noticom",
        service: "play_chime",
        service_data: what,
        return_response: true,
      });
      const { played = [], offline = [], sound, theme } = res.response || {};
      const which = what.chime ? `${sound}${theme ? ` (${theme})` : ""} ` : "";
      if (!played.length && !offline.length) this._toast("No nodes yet. Adopt a node to hear chimes.");
      else if (!played.length) this._toast(`No nodes online (${offline.join(", ")} offline).`);
      else this._toast(`Playing ${which}on ${played.join(", ")}${offline.length ? ` · offline: ${offline.join(", ")}` : ""}`);
    } catch (err) {
      this._toast(`Couldn't play: ${err.message || err}`);
    }
  }

  async _delete(name) {
    const sound = (this._sounds || []).find((c) => c.name === name);
    const used = sound ? sound.used : [];
    const where = used.map((u) => `• ${u.chime} in ${u.theme}`).join("\n");
    const warn = used.length
      ? `\n\nIt's used by:\n${where}\n\nHoliday themes will fall back to their Default sound.` +
        (used.some((u) => u.theme_id === "default") ? " Chimes that use it in Default will have no sound until you pick another." : "")
      : "";
    if (!confirm(`Delete the sound “${name}”?${warn}`)) return;
    try {
      const res = await this._hass.callWS({ type: "noticom/sounds/delete", name });
      this._setSounds(res);
      this._themes = null;
      this._renderList();
      this._toast(`Deleted “${name}”`);
    } catch (err) {
      this._toast(`Couldn't delete: ${err.message || err}`);
    }
  }
}

customElements.define("noticom-panel", NoticomPanel);
