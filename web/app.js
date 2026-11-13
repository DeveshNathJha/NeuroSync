// NeuroSync web UI: router, status bar and shared context. Vanilla JS, no external requests.

import { api, getActiveSession } from "./js/api.js";
import { clear, errorPanel, errorText, h, mmss, notify } from "./js/dom.js";
import * as consent from "./js/views/consent.js";
import * as data from "./js/views/data.js";
import * as history from "./js/views/history.js";
import * as live from "./js/views/live.js";
import * as review from "./js/views/review.js";
import * as video from "./js/views/video.js";

const ROUTES = { consent, live, video, review, history, data };
const STATUS_REFRESH_MS = 15000;
const FALLBACK_DISCLAIMER = "NeuroSync is a research prototype that helps a professional log observable "
  + "behaviours during a session. It does not diagnose or assess any condition. Every suggested event "
  + "must be reviewed by a person.";

const ctx = {
  config: null,
  health: null,
  dirty: false,
  navigate(hash) {
    if (globalThis.location.hash === hash) route();
    else globalThis.location.hash = hash;
  },
  setDirty(value) {
    ctx.dirty = Boolean(value);
  },
  refreshStatus: () => refreshStatus(),
};

let currentView = null;
let currentHash = "";
let suppressNextHashChange = false;
let routeToken = 0;

function parseHash() {
  const parts = globalThis.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map((p) => {
    try {
      return decodeURIComponent(p);
    } catch {
      return p;
    }
  });
  const name = ROUTES[parts[0]] ? parts[0] : "consent";
  return { name, params: parts.slice(1) };
}

function highlightNav(name) {
  for (const link of document.querySelectorAll("#nav a[data-route]")) {
    if (link.dataset.route === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

async function route() {
  const token = ++routeToken;
  if (currentView && typeof currentView.cleanup === "function") currentView.cleanup();
  const { name, params } = parseHash();
  currentView = ROUTES[name];
  currentHash = globalThis.location.hash;
  ctx.setDirty(false);
  highlightNav(name);

  const host = document.getElementById("view");
  clear(host);
  // each render gets its own container: a slow render from a previous route writes into a detached node
  const container = h("div", { class: "view" });
  host.append(container);
  host.setAttribute("aria-busy", "true");
  try {
    await currentView.render(container, ctx, params);
  } catch (err) {
    if (token === routeToken) container.append(errorPanel(err));
  } finally {
    if (token === routeToken) {
      host.removeAttribute("aria-busy");
      const heading = container.querySelector("h1");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus({ preventScroll: true });
      }
    }
  }
}

function onHashChange() {
  if (suppressNextHashChange) {
    suppressNextHashChange = false;
    return;
  }
  if (ctx.dirty && !globalThis.confirm(
    "Your review of this session is not saved to the encrypted store yet. Leave this page anyway?")) {
    suppressNextHashChange = true;
    globalThis.location.hash = currentHash;
    return;
  }
  route();
}

// ------------------------------------------------------------------ status bar

function statusItem(text, kind, href) {
  const cls = `status-item${kind ? ` status-${kind}` : ""}`;
  return href ? h("a", { class: cls, href }, text) : h("span", { class: cls }, text);
}

async function refreshStatus() {
  const box = document.getElementById("status");
  if (!box) return;
  const items = [];
  try {
    const health = await api.health();
    ctx.health = health;
    items.push(health.models_present
      ? statusItem("Models ready", "ok")
      : statusItem("Models missing – run scripts/download_models.py", "bad"));
    items.push(statusItem(health.notes_mode === "llm" ? "Notes: local LLM" : "Notes: template", ""));
    items.push(health.mic_available ? statusItem("Microphone ready", "ok") : statusItem("No microphone", "warn"));
    if (health.camera_busy) items.push(statusItem("Camera in use", "warn"));
  } catch (err) {
    items.push(statusItem(errorText(err), "bad"));
  }

  try {
    const sessions = await api.sessions();
    const running = (sessions || []).find((s) => s.state === "running");
    if (running) {
      items.push(statusItem(`● Recording ${mmss(running.elapsed_s)}`, "live",
        `#/live/${encodeURIComponent(running.session_id)}`));
    } else {
      const active = getActiveSession();
      const open = (sessions || []).find((s) => active && s.session_id === active.id);
      if (open) items.push(statusItem("Open session", "", `#/review/${encodeURIComponent(open.session_id)}`));
    }
  } catch {
    // session list is optional for the status bar
  }
  box.replaceChildren(...items);
}

// ------------------------------------------------------------------ boot

async function boot() {
  try {
    ctx.config = await api.config();
  } catch (err) {
    ctx.config = { disclaimer: FALLBACK_DISCLAIMER, event_labels: {}, max_duration_min: 90 };
    notify(`Could not load the configuration: ${errorText(err)}`, "error");
  }
  const disclaimer = document.getElementById("disclaimer");
  if (disclaimer) disclaimer.textContent = ctx.config.disclaimer || FALLBACK_DISCLAIMER;

  globalThis.addEventListener("hashchange", onHashChange);
  globalThis.addEventListener("beforeunload", (e) => {
    if (ctx.dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  refreshStatus();
  setInterval(refreshStatus, STATUS_REFRESH_MS);

  if (!globalThis.location.hash) {
    globalThis.history.replaceState(null, "", "#/consent");
  }
  route();
}

if (typeof document !== "undefined") boot();
