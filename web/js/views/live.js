// View: Live webcam session. Updates over a WebSocket, falling back to polling.

import { STREAM_PATH, api, getActiveSession, liveSocketUrl } from "../api.js";
import { emptyState, errorPanel, errorText, h, mmss, notify, pageHeader, pct, setText, withBusy } from "../dom.js";

const POLL_MS = 500;
const WS_FIRST_MESSAGE_MS = 2500;

let teardown = [];

export function cleanup() {
  for (const fn of teardown.splice(0)) {
    try {
      fn();
    } catch {
      // nothing to do: the view is going away
    }
  }
}

function sessionIdFrom(params) {
  if (params[0]) return params[0];
  const active = getActiveSession();
  return active && active.mode === "live" ? active.id : null;
}

export async function render(root, ctx, params) {
  const id = sessionIdFrom(params);
  if (!id) {
    root.append(pageHeader("Live session"),
      emptyState("No live session yet", "Create a consent record and choose “Live webcam session”.",
        "#/consent", "Go to consent & setup"));
    return;
  }

  let session;
  try {
    session = await api.session(id);
  } catch (err) {
    root.append(pageHeader("Live session"), errorPanel(err, "Could not open this session"));
    return;
  }
  if (!root.isConnected) return;

  if (session.mode !== "live") {
    root.append(pageHeader("Live session"),
      emptyState("This is a video session", "This session analyses an uploaded video.",
        `#/video/${encodeURIComponent(id)}`, "Open the video page"));
    return;
  }
  if (session.ended_at) {
    root.append(pageHeader("Live session"),
      emptyState("This session has ended", "Its suggested events are ready for review.",
        `#/review/${encodeURIComponent(id)}`, "Review the session"));
    return;
  }

  buildLiveView(root, ctx, id, session);
}

function buildLiveView(root, ctx, id, session) {
  const labels = ctx.config?.event_labels || {};
  const maxS = session.max_duration_s || (ctx.config?.max_duration_min ?? 90) * 60;
  const ui = createLayout(session, maxS);
  root.append(ui.page);

  const live = { running: session.state === "running", finished: false, ws: null, poll: null, wsTimer: null };
  const barRows = new Map();
  let lastError = "";

  // -------------------------------------------------------------- video stream
  function attachStream() {
    ui.img.src = `${STREAM_PATH}?t=${Date.now()}`;
    ui.img.hidden = false;
    ui.placeholder.hidden = true;
  }
  function detachStream() {
    ui.img.removeAttribute("src");
    ui.img.hidden = true;
    ui.placeholder.hidden = false;
  }

  // -------------------------------------------------------------- updates
  function stopUpdates() {
    if (live.ws) {
      live.ws.onclose = null;
      live.ws.onmessage = null;
      live.ws.onerror = null;
      try {
        live.ws.close();
      } catch {
        // already closed
      }
      live.ws = null;
    }
    clearTimeout(live.wsTimer);
    clearInterval(live.poll);
    live.poll = null;
  }

  function startPolling() {
    if (live.poll || live.finished) return;
    live.poll = setInterval(async () => {
      try {
        handleState(await api.liveState(id));
      } catch (err) {
        showError(errorText(err));
      }
    }, POLL_MS);
  }

  function startUpdates() {
    stopUpdates();
    if (!("WebSocket" in globalThis)) {
      startPolling();
      return;
    }
    let ws;
    try {
      ws = new WebSocket(liveSocketUrl(id));
    } catch {
      startPolling();
      return;
    }
    live.ws = ws;
    live.wsTimer = setTimeout(() => startPolling(), WS_FIRST_MESSAGE_MS);
    ws.onmessage = (msg) => {
      clearTimeout(live.wsTimer);
      try {
        handleState(JSON.parse(msg.data));
      } catch {
        // ignore malformed frames
      }
    };
    ws.onclose = () => {
      live.ws = null;
      if (!live.finished) startPolling();
    };
    ws.onerror = () => {
      // onclose follows and switches to polling
    };
  }

  teardown.push(stopUpdates, detachStream);

  // -------------------------------------------------------------- rendering
  function showError(text) {
    if (text && text !== lastError) {
      ui.error.textContent = text;
      ui.error.hidden = false;
    } else if (!text) {
      ui.error.hidden = true;
    }
    lastError = text || "";
  }

  function updateBars(scores) {
    for (const [kind, value] of Object.entries(scores || {})) {
      let row = barRows.get(kind);
      if (!row) {
        const bar = h("progress", { max: 1, value: 0, "aria-label": labels[kind] || kind });
        const val = h("span", { class: "bar-value" }, "0%");
        row = { bar, val };
        barRows.set(kind, row);
        ui.bars.append(h("div", { class: "bar-row" }, h("span", { class: "bar-label" }, labels[kind] || kind), bar, val));
      }
      const v = Math.max(0, Math.min(1, Number(value) || 0));
      row.bar.value = v;
      setText(row.val, pct(v));
      row.bar.classList.toggle("is-active", v >= 0.5);
    }
  }

  function updateHeartRate(state) {
    if (state.heart_rate !== null && state.heart_rate !== undefined && state.hr_reliable) {
      setText(ui.hrValue, `${Math.round(state.heart_rate)} BPM`);
      ui.hrValue.classList.remove("muted");
    } else {
      setText(ui.hrValue, "unreliable – improve lighting / keep face visible");
      ui.hrValue.classList.add("muted");
    }
    const parts = [];
    if (Number.isFinite(state.hr_snr_db)) parts.push(`signal quality ${state.hr_snr_db.toFixed(1)} dB`);
    if (Number.isFinite(state.baseline_hr)) parts.push(`baseline ${Math.round(state.baseline_hr)} BPM`);
    setText(ui.hrSub, parts.join(" · ") || "No baseline yet");
    if (state.baseline_measuring) {
      ui.baselineBtn.disabled = true;
      setText(ui.baselineStatus, `Measuring resting baseline… ${Math.ceil(state.baseline_remaining_s || 0)} s left`);
    } else {
      ui.baselineBtn.disabled = !live.running;
      setText(ui.baselineStatus, Number.isFinite(state.baseline_hr) ? "Baseline set." : "");
    }
  }

  function updateLoudness(dbfs) {
    if (Number.isFinite(dbfs)) {
      ui.loudMeter.value = Math.max(-60, Math.min(0, dbfs));
      setText(ui.loudValue, `${dbfs.toFixed(0)} dBFS`);
    } else {
      ui.loudMeter.value = -60;
      setText(ui.loudValue, ctx.health?.mic_available === false ? "no microphone" : "–");
    }
  }

  function updateVisibility(state) {
    const hints = [];
    if (state.face_visible === false) hints.push("Face not visible: heart rate and head signals are paused.");
    if (state.body_visible === false) hints.push("Upper body not visible: hand/arm signals are paused.");
    ui.visibility.replaceChildren(...hints.map((t) => h("li", {}, t)));
    ui.visibility.hidden = hints.length === 0;
  }

  function updateEvents(state) {
    const count = Array.isArray(state.suggested_events) ? state.suggested_events.length : Number(state.suggested_events) || 0;
    setText(ui.eventCount, `${count} suggested`);
    const recent = Array.isArray(state.recent_events) ? state.recent_events.slice(-10).reverse() : [];
    ui.events.replaceChildren(...(recent.length
      ? recent.map((e) => h("li", {},
        h("span", { class: "ev-time" }, mmss(e.start)),
        h("span", { class: "ev-label" }, e.label || labels[e.kind] || e.kind),
        h("span", { class: "ev-conf" }, pct(e.confidence))))
      : [h("li", { class: "muted" }, "No suggestions yet.")]));
  }

  function handleState(state) {
    if (!state || live.finished) return;
    setText(ui.timer, `${mmss(state.elapsed_s)} / ${mmss(state.max_s || maxS)}`);
    ui.timeBar.max = state.max_s || maxS;
    ui.timeBar.value = Math.min(state.elapsed_s || 0, ui.timeBar.max);
    updateBars(state.behaviour_scores);
    updateHeartRate(state);
    updateLoudness(state.loudness_dbfs);
    updateVisibility(state);
    updateEvents(state);
    showError(state.error || "");
    if (state.time_limit_reached) {
      finish("The maximum session duration was reached; the session stopped automatically.");
    } else if (live.running && state.running === false) {
      finish("The session stopped.");
    }
  }

  // -------------------------------------------------------------- actions
  function setRunning(running) {
    live.running = running;
    ui.startBtn.hidden = running;
    ui.stopBtn.hidden = !running;
    ui.baselineBtn.disabled = !running;
    setText(ui.stateBadge, running ? "Recording" : "Ready");
    ui.stateBadge.classList.toggle("badge-live", running);
  }

  async function finish(message) {
    if (live.finished) return;
    live.finished = true;
    stopUpdates();
    detachStream();
    try {
      await api.liveStop(id);
    } catch (err) {
      if (err.status !== 409) notify(errorText(err), "error");
    }
    if (message) notify(message, "info");
    ctx.refreshStatus?.();
    ctx.navigate(`#/review/${encodeURIComponent(id)}`);
  }

  ui.startBtn.addEventListener("click", (e) => withBusy(e.currentTarget, "Starting…", async () => {
    try {
      await api.liveStart(id);
      setRunning(true);
      attachStream();
      startUpdates();
      ctx.refreshStatus?.();
    } catch (err) {
      notify(errorText(err), "error");
    }
  }));

  ui.stopBtn.addEventListener("click", (e) => withBusy(e.currentTarget, "Stopping…", () => finish("")));

  ui.baselineBtn.addEventListener("click", async () => {
    try {
      await api.liveBaseline(id);
      setText(ui.baselineStatus, "Measuring resting baseline… please stay still and face the camera.");
      ui.baselineBtn.disabled = true;
    } catch (err) {
      notify(errorText(err), "error");
    }
  });

  setRunning(live.running);
  if (live.running) {
    attachStream();
    startUpdates();
  }
}

function createLayout(session, maxS) {
  const subjectId = session.consent?.subject_id || "–";
  const ui = {};
  ui.stateBadge = h("span", { class: "badge" }, "Ready");
  ui.timer = h("span", { class: "timer", "aria-live": "off" }, `00:00 / ${mmss(maxS)}`);
  ui.timeBar = h("progress", { class: "time-bar", max: maxS, value: 0, "aria-label": "Session time used" });
  ui.startBtn = h("button", { type: "button", class: "btn btn-primary" }, "Start session");
  ui.stopBtn = h("button", { type: "button", class: "btn btn-danger", hidden: true }, "Stop session");
  ui.baselineBtn = h("button", { type: "button", class: "btn", disabled: true }, "Measure resting baseline (60 s)");
  ui.baselineStatus = h("p", { class: "hint", "aria-live": "polite" });
  ui.img = h("img", { class: "stream", alt: "Live camera preview with detected landmarks", hidden: true });
  ui.placeholder = h("div", { class: "stream-placeholder" }, "The camera preview appears when the session starts.");
  ui.error = h("p", { class: "form-error", role: "alert", hidden: true });
  ui.bars = h("div", { class: "bars" });
  ui.hrValue = h("p", { class: "big-value muted" }, "–");
  ui.hrSub = h("p", { class: "hint" }, "No baseline yet");
  ui.loudMeter = h("meter", { min: -60, max: 0, low: -30, high: -20, optimum: -60, value: -60, "aria-label": "Loudness" });
  ui.loudValue = h("span", { class: "bar-value" }, "–");
  ui.visibility = h("ul", { class: "visibility", hidden: true, "aria-live": "polite" });
  ui.eventCount = h("span", { class: "badge" }, "0 suggested");
  ui.events = h("ol", { class: "event-feed", "aria-live": "polite" }, h("li", { class: "muted" }, "No suggestions yet."));

  ui.page = h("div", { class: "live" },
    pageHeader("Live session", `Subject ${subjectId}`),
    h("div", { class: "toolbar" },
      ui.stateBadge, ui.timer, ui.timeBar,
      h("div", { class: "toolbar-actions" }, ui.startBtn, ui.stopBtn)),
    ui.error,
    h("div", { class: "live-grid" },
      h("section", { class: "panel stream-panel", "aria-label": "Camera preview" },
        ui.img, ui.placeholder, ui.visibility),
      h("div", { class: "cards" },
        h("section", { class: "panel card" }, h("h2", {}, "Movement patterns"), ui.bars,
          h("p", { class: "hint" }, "Scores above 50% mean the pattern is currently being seen.")),
        h("section", { class: "panel card" }, h("h2", {}, "Heart rate (webcam)"), ui.hrValue, ui.hrSub,
          ui.baselineBtn, ui.baselineStatus),
        h("section", { class: "panel card" }, h("h2", {}, "Loudness"),
          h("div", { class: "bar-row" }, ui.loudMeter, ui.loudValue)),
        h("section", { class: "panel card" },
          h("h2", {}, "Suggested events ", ui.eventCount), ui.events,
          h("p", { class: "hint" }, "You confirm or reject each suggestion after the session.")))));
  return ui;
}
