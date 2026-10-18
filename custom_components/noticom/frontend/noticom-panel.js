// Noticom sidebar panel. Plain web component, no build step.
// Uses Home Assistant's theme variables so it follows light/dark themes.

const UPLOAD_URL = "/api/noticom/panel/chimes";
const PREVIEW_URL = (hash) => `/api/noticom/panel/chime/${hash}`;
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
    this._chimes = null;
    this._file = null;
    this._busy = false;
    this._audio = null;
    this._playingKey = null;
    this._tab = "chimes";
    this._intercom = null;
    this._poll = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._render();
      this._load();
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
    if (this._hass && this._tab === "intercom") this._showTab("intercom");
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  async _load() {
    try {
      const res = await this._hass.callWS({ type: "noticom/chimes/list" });
      this._chimes = res.chimes;
    } catch (err) {
      this._chimes = [];
      this._toast(`Couldn't load chimes: ${err.message || err}`);
    }
    this._renderList();
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
        <button class="tab" role="tab" data-tab="chimes" aria-selected="true">Chimes</button>
        <button class="tab" role="tab" data-tab="intercom" aria-selected="false">Intercom</button>
        <button class="tab" role="tab" data-tab="settings" aria-selected="false">Settings</button>
      </nav>
      <main>
      <section data-panel="chimes">
        <div class="section-head">
          <h2>Chimes</h2>
        </div>
        <p class="hint" style="margin:0 4px 16px">
          Notification sounds your automations can play on any node with
          <code>noticom.play_chime</code>. Upload WAV or MP3 files; each is
          evened out in loudness and copied to every node ahead of time.
        </p>

        <div class="card upload">
          <div class="drop" tabindex="0" role="button" aria-label="Choose a WAV or MP3 file">
            <ha-icon icon="mdi:upload"></ha-icon>
            <strong class="drop-title">Choose a WAV or MP3 file</strong>
            <span class="hint drop-sub">or drag one here · up to 10 MB</span>
          </div>
          <input type="file" accept="${ACCEPT}" hidden>
          <div class="row">
            <label class="field">Chime name
              <input type="text" class="name-input" maxlength="48" placeholder="e.g. mailbox" autocomplete="off" spellcheck="false">
            </label>
            <button class="primary upload-btn" disabled><ha-icon icon="mdi:check"></ha-icon>Upload</button>
          </div>
          <label class="replace" hidden><input type="checkbox" class="replace-box"> Replace the existing chime with this name</label>
          <div class="msg" role="status" aria-live="polite"></div>
        </div>

        <div class="card">
          <div class="list-head"><span>Your chimes</span><span class="count"></span></div>
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
              <div class="hint">Plays before every message.</div>
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
            <div class="ctl"><input type="number" id="d-button_pin" min="2" max="27" step="1"><span class="hint">13: HAT Grove connector · 17: HAT onboard button</span></div>
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
    this._message("");
    this._validate();
    nameInput.focus();
    nameInput.select();
  }

  _existing(name) {
    const key = name.trim().toLowerCase();
    return (this._chimes || []).find((c) => c.name.toLowerCase() === key);
  }

  _validate() {
    const root = this.shadowRoot;
    const name = root.querySelector(".name-input").value.trim();
    const replaceRow = root.querySelector(".replace");
    const exists = name && this._existing(name);
    replaceRow.hidden = !exists;
    let error = "";
    if (name && !NAME_RE.test(name)) {
      error = "Use letters, numbers, spaces, - and _ (start with a letter or number).";
    } else if (exists && !root.querySelector(".replace-box").checked) {
      error = `A chime named “${exists.name}” already exists.`;
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
    form.append("file", this._file, this._file.name);
    this._busy = true;
    btn.disabled = true;
    this._message("Uploading and converting…");
    let failure = "";
    try {
      const resp = await this._hass.fetchWithAuth(UPLOAD_URL, { method: "POST", body: form });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(body.error || `Upload failed (${resp.status})`);
      this._chimes = body.chimes;
      this._file = null;
      root.querySelector(".drop-title").textContent = "Choose a WAV or MP3 file";
      root.querySelector(".drop-sub").textContent = "or drag one here · up to 10 MB";
      root.querySelector(".name-input").value = "";
      root.querySelector(".replace").hidden = true;
      this._message(`Added “${body.chime}”. Nodes are downloading it now.`);
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
    const chimes = this._chimes || [];
    root.querySelector(".count").textContent = chimes.length ? `${chimes.length}` : "";
    if (!chimes.length) {
      list.innerHTML = `<div class="empty"><ha-icon icon="mdi:bell-off-outline"></ha-icon>No chimes yet. Upload one above.</div>`;
      return;
    }
    list.innerHTML = `<ul>${chimes
      .map(
        (c) => `
        <li data-name="${esc(c.name)}" data-hash="${esc(c.hash)}">
          <div class="info">
            <div class="name">${esc(c.name)}</div>
            <div class="meta">${c.duration.toFixed(1)} s · <code>chime: ${esc(c.name)}</code></div>
          </div>
          <div class="actions">
            <button class="preview icon-only-narrow" aria-label="Preview ${esc(c.name)} here">
              <ha-icon icon="${this._playingKey === c.hash ? "mdi:stop" : "mdi:play"}"></ha-icon><span class="label">${this._playingKey === c.hash ? "Stop" : "Preview"}</span>
            </button>
            <button class="test icon-only-narrow" aria-label="Play ${esc(c.name)} on all nodes">
              <ha-icon icon="mdi:bullhorn-outline"></ha-icon><span class="label">Play on nodes</span>
            </button>
            <button class="danger delete icon-only-narrow" aria-label="Delete ${esc(c.name)}">
              <ha-icon icon="mdi:delete-outline"></ha-icon><span class="label">Delete</span>
            </button>
          </div>
        </li>`
      )
      .join("")}</ul>`;
    list.querySelectorAll("li").forEach((li) => {
      const { name, hash } = li.dataset;
      li.querySelector(".preview").addEventListener("click", () => this._preview(hash, PREVIEW_URL(hash)));
      li.querySelector(".test").addEventListener("click", () => this._playOnNodes(name));
      li.querySelector(".delete").addEventListener("click", () => this._delete(name));
    });
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
    this._renderList();
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
    } else {
      this._load();
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
                ${n.ptt_enabled ? "" : `<span class="badge">Push to talk off</span>`}
              </div>
              <select class="ic-mode" aria-label="Who ${esc(n.name)} can talk to" ${others.length ? "" : "disabled"}>
                <option value="all" ${all ? "selected" : ""}>All nodes</option>
                <option value="some" ${all ? "" : "selected"}>Only selected nodes</option>
              </select>
            </div>
            ${!others.length
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
        el.querySelector(".ic-mode").addEventListener("change", (e) => {
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

  _applySettings(st) {
    const root = this.shadowRoot;
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
      if (!Number.isInteger(pin) || pin < 2 || pin > 27) {
        this._settingsMsg("Button GPIO pin must be a whole number from 2 to 27.", true);
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

  async _playOnNodes(name) {
    try {
      const res = await this._hass.callWS({
        type: "call_service",
        domain: "noticom",
        service: "play_chime",
        service_data: { chime: name },
        return_response: true,
      });
      const { played = [], offline = [] } = res.response || {};
      if (!played.length && !offline.length) this._toast("No nodes yet. Adopt a node to hear chimes.");
      else if (!played.length) this._toast(`No nodes online (${offline.join(", ")} offline).`);
      else this._toast(`Playing on ${played.join(", ")}${offline.length ? ` · offline: ${offline.join(", ")}` : ""}`);
    } catch (err) {
      this._toast(`Couldn't play: ${err.message || err}`);
    }
  }

  async _delete(name) {
    if (!confirm(`Delete the chime “${name}”?\n\nAutomations that play it will stop working until you add a chime with the same name.`)) return;
    try {
      const res = await this._hass.callWS({ type: "noticom/chimes/delete", name });
      this._chimes = res.chimes;
      this._renderList();
      this._toast(`Deleted “${name}”`);
    } catch (err) {
      this._toast(`Couldn't delete: ${err.message || err}`);
    }
  }
}

customElements.define("noticom-panel", NoticomPanel);
