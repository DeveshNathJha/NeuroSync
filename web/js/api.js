// Client for the local NeuroSync API (same origin). No other host is ever contacted.

const ACTOR_KEY = "neurosync.actor";
const ACTIVE_KEY = "neurosync.activeSession";
const enc = encodeURIComponent;

export const STREAM_PATH = "/api/live/stream.mjpg";

// ------------------------------------------------------------------ local storage (best effort)

function storageGet(key) {
  try {
    return globalThis.localStorage ? globalThis.localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}

function storageSet(key, value) {
  try {
    if (!globalThis.localStorage) return;
    if (value === null || value === undefined) globalThis.localStorage.removeItem(key);
    else globalThis.localStorage.setItem(key, value);
  } catch {
    // private mode / blocked storage: the app still works, it just won't remember
  }
}

export function getActor() {
  return storageGet(ACTOR_KEY) || "";
}

export function setActor(name) {
  storageSet(ACTOR_KEY, name ? String(name).trim() : null);
}

/** The session created most recently in this browser: {id, mode}. */
export function getActiveSession() {
  const raw = storageGet(ACTIVE_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    return value && value.id ? value : null;
  } catch {
    return null;
  }
}

export function setActiveSession(value) {
  storageSet(ACTIVE_KEY, value ? JSON.stringify(value) : null);
}

// ------------------------------------------------------------------ requests

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** HTTP header values must be ISO-8859-1; keep the recorder name printable ASCII. */
function actorHeader() {
  const clean = getActor().replace(/[^\x20-\x7E]/g, "").trim().slice(0, 100);
  return clean || "local-user";
}

function headers(extra) {
  return { "X-Actor": actorHeader(), ...(extra || {}) };
}

function detailFromText(text, status, statusText) {
  if (text) {
    try {
      const data = JSON.parse(text);
      const detail = data.detail ?? data.message ?? data.error;
      if (Array.isArray(detail)) {
        return detail.map((d) => {
          if (d && d.msg) {
            const where = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
            return where ? `${where}: ${d.msg}` : d.msg;
          }
          return String(d);
        }).join("; ");
      }
      if (detail) return typeof detail === "string" ? detail : JSON.stringify(detail);
    } catch {
      return text.slice(0, 300);
    }
  }
  return `${status} ${statusText || "Request failed"}`;
}

async function detailOf(res) {
  let text = "";
  try {
    text = await res.text();
  } catch {
    // body unavailable
  }
  return detailFromText(text, res.status, res.statusText);
}

const UNREACHABLE = "The NeuroSync server is not reachable. Is it still running?";

export async function request(method, path, body) {
  const init = { method, headers: headers({ Accept: "application/json" }) };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!res.ok) throw new ApiError(res.status, await detailOf(res));
  if (res.status === 204) return null;
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

export const api = {
  health: () => request("GET", "/api/health"),
  config: () => request("GET", "/api/config"),

  createSession: (body) => request("POST", "/api/sessions", body),
  sessions: () => request("GET", "/api/sessions"),
  session: (id) => request("GET", `/api/sessions/${enc(id)}`),
  discard: (id) => request("DELETE", `/api/sessions/${enc(id)}`),

  liveStart: (id) => request("POST", `/api/sessions/${enc(id)}/live/start`),
  liveBaseline: (id) => request("POST", `/api/sessions/${enc(id)}/live/baseline`),
  liveStop: (id) => request("POST", `/api/sessions/${enc(id)}/live/stop`),
  liveState: (id) => request("GET", `/api/sessions/${enc(id)}/live/state`),

  videoStatus: (id) => request("GET", `/api/sessions/${enc(id)}/video/status`),

  patchEvent: (id, eventId, body) => request("PATCH", `/api/sessions/${enc(id)}/events/${enc(eventId)}`, body),
  bulk: (id, body) => request("POST", `/api/sessions/${enc(id)}/events/bulk`, body),
  save: (id) => request("POST", `/api/sessions/${enc(id)}/save`),
  notes: (id, audience) => request("POST", `/api/sessions/${enc(id)}/notes`, { audience }),

  subjects: () => request("GET", "/api/subjects"),
  subjectSessions: (subjectId) => request("GET", `/api/subjects/${enc(subjectId)}/sessions`),
  trends: (subjectId) => request("GET", `/api/subjects/${enc(subjectId)}/trends`),
  deleteSubject: (subjectId) => request("DELETE", `/api/subjects/${enc(subjectId)}?confirm=${enc(subjectId)}`),

  stored: (sessionId) => request("GET", `/api/stored/${enc(sessionId)}`),
  deleteStored: (sessionId) => request("DELETE", `/api/stored/${enc(sessionId)}`),

  purge: () => request("POST", "/api/data/purge"),
  dataInfo: () => request("GET", "/api/data/info"),
  audit: (limit = 200) => request("GET", `/api/audit?limit=${enc(limit)}`),
  auditVerify: () => request("GET", "/api/audit/verify"),
};

export function exportPath(id, fmt, { stored = false, audience } = {}) {
  const base = stored ? `/api/stored/${enc(id)}` : `/api/sessions/${enc(id)}`;
  const query = audience ? `?audience=${enc(audience)}` : "";
  return `${base}/export/${enc(fmt)}${query}`;
}

export function subjectExportPath(subjectId) {
  return `/api/subjects/${enc(subjectId)}/export`;
}

function filenameFrom(disposition) {
  if (!disposition) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      // fall through to the plain filename
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain ? plain[1] : null;
}

/** Download a file from the API (keeps the X-Actor header, which a plain link can't send). */
export async function download(path, fallbackName) {
  let res;
  try {
    res = await fetch(path, { headers: headers() });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!res.ok) throw new ApiError(res.status, await detailOf(res));
  const blob = await res.blob();
  const name = filenameFrom(res.headers.get("content-disposition")) || fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Upload a video with progress. Returns {promise, abort}. */
export function uploadVideo(id, file, onProgress) {
  const xhr = new XMLHttpRequest();
  const promise = new Promise((resolve, reject) => {
    xhr.open("POST", `/api/sessions/${enc(id)}/video`);
    for (const [key, value] of Object.entries(headers({ Accept: "application/json" }))) {
      xhr.setRequestHeader(key, value);
    }
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        let data = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          data = null;
        }
        resolve(data);
      } else {
        reject(new ApiError(xhr.status, detailFromText(xhr.responseText, xhr.status, xhr.statusText)));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, UNREACHABLE));
    xhr.onabort = () => reject(new ApiError(0, "Upload cancelled."));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}

export function liveSocketUrl(id) {
  const proto = globalThis.location && globalThis.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${globalThis.location.host}/api/sessions/${enc(id)}/live/ws`;
}
