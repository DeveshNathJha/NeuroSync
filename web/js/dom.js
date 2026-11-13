// DOM helpers. Every piece of text goes through textContent / createTextNode,
// never innerHTML, so data from the API can't inject markup.

const SVG_NS = "http://www.w3.org/2000/svg";

export function h(tag, attrs, ...children) {
  return build(document.createElement(tag), attrs, children);
}

export function s(tag, attrs, ...children) {
  return build(document.createElementNS(SVG_NS, tag), attrs, children);
}

function build(el, attrs, children) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key === "style" && typeof value === "object") Object.assign(el.style, value); // CSSOM, CSP-safe
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function setText(el, text) {
  if (el) el.textContent = text === null || text === undefined ? "" : String(text);
}

// ------------------------------------------------------------------ formatting

export function mmss(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return "–";
  const total = Math.max(0, Math.round(Number(seconds)));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function span(start, end) {
  return `${mmss(start)}–${mmss(end)}`;
}

export function duration(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return "–";
  const sec = Number(seconds);
  if (sec >= 3600) return `${(sec / 3600).toFixed(1)} h`;
  return `${mmss(sec)} min`;
}

export function fmtDate(epochSeconds) {
  if (!epochSeconds) return "–";
  const d = new Date(Number(epochSeconds) * 1000);
  return Number.isNaN(d.getTime()) ? "–" : d.toLocaleString();
}

export function fmtShortDate(epochSeconds) {
  if (!epochSeconds) return "–";
  const d = new Date(Number(epochSeconds) * 1000);
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

export function pct(x) {
  if (x === null || x === undefined || !Number.isFinite(Number(x))) return "–";
  return `${Math.round(Number(x) * 100)}%`;
}

export function bpm(x) {
  if (x === null || x === undefined || !Number.isFinite(Number(x))) return "–";
  return `${Math.round(Number(x))} BPM`;
}

export function countOf(value) {
  if (Array.isArray(value)) return value.length;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

// ------------------------------------------------------------------ messages

export function errorText(err) {
  if (!err) return "Something went wrong.";
  return err.message ? err.message : String(err);
}

/** Show a dismissible message in the aria-live region at the top of the page. */
export function notify(text, kind = "info") {
  const region = document.getElementById("messages");
  if (!region) return;
  const msg = h("div", { class: `msg msg-${kind}`, role: kind === "error" ? "alert" : "status" },
    h("span", { class: "msg-text" }, text),
    h("button", {
      type: "button", class: "msg-close", "aria-label": "Dismiss message",
      onclick: () => msg.remove(),
    }, "×"));
  region.append(msg);
  while (region.children.length > 4) region.firstElementChild.remove();
  if (kind !== "error") setTimeout(() => msg.remove(), 7000);
}

export function errorPanel(err, title = "Could not load this page") {
  return h("div", { class: "panel panel-error", role: "alert" },
    h("h2", {}, title),
    h("p", {}, errorText(err)));
}

export function emptyState(title, text, linkHref, linkText) {
  return h("div", { class: "panel empty" },
    h("h2", {}, title),
    h("p", {}, text),
    linkHref ? h("a", { class: "btn btn-primary", href: linkHref }, linkText) : null);
}

export function pageHeader(title, subtitle) {
  return h("header", { class: "page-header" },
    h("h1", {}, title),
    subtitle ? h("p", { class: "subtitle" }, subtitle) : null);
}

/** Run an async action with a button disabled and a busy label, re-enabled afterwards. */
export async function withBusy(button, busyLabel, action) {
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  if (busyLabel) button.textContent = busyLabel;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = original;
  }
}
