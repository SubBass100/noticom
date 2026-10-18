// Noticom sidebar panel. Plain web component, no build step.
// Uses Home Assistant's theme variables so it follows light/dark themes.

const UPLOAD_URL = "/api/noticom/panel/chimes";
const PREVIEW_URL = (hash) => `/api/noticom/panel/chime/${hash}`;
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
    this._playingHash = null;
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
      <main>
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
      </main>
    `;

    const root = this.shadowRoot;
    const menu = root.querySelector("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;

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
              <ha-icon icon="${this._playingHash === c.hash ? "mdi:stop" : "mdi:play"}"></ha-icon><span class="label">${this._playingHash === c.hash ? "Stop" : "Preview"}</span>
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
      li.querySelector(".preview").addEventListener("click", () => this._preview(hash));
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
    this._playingHash = null;
  }

  async _preview(hash) {
    const wasPlaying = this._playingHash === hash;
    this._stopPreview();
    if (wasPlaying) { this._renderList(); return; }
    try {
      const resp = await this._hass.fetchWithAuth(PREVIEW_URL(hash));
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const audio = new Audio(URL.createObjectURL(await resp.blob()));
      audio.addEventListener("ended", () => { this._stopPreview(); this._renderList(); });
      this._audio = audio;
      this._playingHash = hash;
      this._renderList();
      await audio.play();
    } catch (err) {
      this._stopPreview();
      this._renderList();
      this._toast(`Couldn't preview: ${err.message || err}`);
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
