// View: Analyse a recorded video (secondary mode).

import { api, getActiveSession, uploadVideo } from "../api.js";
import { emptyState, errorPanel, errorText, h, notify, pageHeader, pct, setText } from "../dom.js";

const POLL_MS = 700;
// the API reports a finished analysis as state "stopped" with progress 1.0
const DONE_STATES = new Set(["stopped", "done", "finished", "complete", "completed", "analysed"]);
const ACCEPT = "video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi";

let teardown = [];

export function cleanup() {
  for (const fn of teardown.splice(0)) {
    try {
      fn();
    } catch {
      // view is going away
    }
  }
}

function sessionIdFrom(params) {
  if (params[0]) return params[0];
  const active = getActiveSession();
  return active && active.mode === "video" ? active.id : null;
}

function sizeText(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export async function render(root, ctx, params) {
  const id = sessionIdFrom(params);
  if (!id) {
    root.append(pageHeader("Analyse a video"),
      emptyState("No video session yet", "Create a consent record and choose “Analyse a recorded video”.",
        "#/consent", "Go to consent & setup"));
    return;
  }

  let session;
  try {
    session = await api.session(id);
  } catch (err) {
    root.append(pageHeader("Analyse a video"), errorPanel(err, "Could not open this session"));
    return;
  }
  if (!root.isConnected) return;
  if (session.mode !== "video") {
    root.append(pageHeader("Analyse a video"),
      emptyState("This is a live session", "This session uses the webcam.",
        `#/live/${encodeURIComponent(id)}`, "Open the live session"));
    return;
  }

  const deleteAfter = ctx.config?.delete_video_after_analysis !== false;
  const keeps = Boolean(session.consent?.video_stored) && !deleteAfter;
  const ui = buildLayout(session, keeps);
  root.append(ui.page);

  let selected = null;
  let upload = null;
  let poll = null;
  teardown.push(() => {
    if (upload) upload.abort();
    clearInterval(poll);
  });

  function choose(file) {
    if (!file) return;
    if (!/\.(mp4|mov|avi)$/i.test(file.name) && !/^video\//.test(file.type)) {
      notify("Please choose an MP4, MOV or AVI video.", "error");
      return;
    }
    selected = file;
    setText(ui.fileName, `${file.name} (${sizeText(file.size)})`);
    ui.startBtn.disabled = false;
  }

  ui.input.addEventListener("change", () => choose(ui.input.files[0]));
  ui.drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    ui.drop.classList.add("is-over");
  });
  ui.drop.addEventListener("dragleave", () => ui.drop.classList.remove("is-over"));
  ui.drop.addEventListener("drop", (e) => {
    e.preventDefault();
    ui.drop.classList.remove("is-over");
    choose(e.dataTransfer?.files?.[0]);
  });

  function setStage(text, value) {
    setText(ui.stage, text);
    if (value === null) ui.progress.removeAttribute("value");
    else ui.progress.value = value;
    setText(ui.progressText, value === null ? "" : pct(value));
  }

  async function checkStatus() {
    let st;
    try {
      st = await api.videoStatus(id);
    } catch (err) {
      clearInterval(poll);
      poll = null;
      showFailure(errorText(err));
      return;
    }
    if (st.error || st.state === "error" || st.state === "failed") {
      clearInterval(poll);
      poll = null;
      showFailure(st.error || "The analysis failed.");
      return;
    }
    const progress = Number(st.progress);
    setStage("Analysing the video on this computer…", Number.isFinite(progress) ? Math.min(1, progress) : null);
    if (DONE_STATES.has(String(st.state)) || (Number.isFinite(progress) && progress >= 1 && st.state !== "running")) {
      clearInterval(poll);
      poll = null;
      notify(st.video_kept ? "Analysis finished. The video was kept, as consented."
        : "Analysis finished. The uploaded video was deleted.", "success");
      ctx.refreshStatus?.();
      ctx.navigate(`#/review/${encodeURIComponent(id)}`);
    }
  }

  function showFailure(text) {
    ui.error.textContent = text;
    ui.error.hidden = false;
    ui.startBtn.disabled = !selected;
    ui.input.disabled = false;
  }

  ui.startBtn.addEventListener("click", async () => {
    if (!selected) return;
    ui.error.hidden = true;
    ui.startBtn.disabled = true;
    ui.input.disabled = true;
    ui.progressBox.hidden = false;
    setStage("Uploading to the local server…", 0);
    upload = uploadVideo(id, selected, (frac) => setStage("Uploading to the local server…", frac));
    try {
      await upload.promise;
    } catch (err) {
      upload = null;
      showFailure(errorText(err));
      return;
    }
    upload = null;
    setStage("Analysing the video on this computer…", 0);
    poll = setInterval(checkStatus, POLL_MS);
    checkStatus();
  });
}

function buildLayout(session, keeps) {
  const ui = {};
  ui.input = h("input", { id: "video-file", type: "file", accept: ACCEPT, class: "visually-hidden" });
  ui.fileName = h("span", { class: "file-name" }, "No file chosen");
  ui.drop = h("label", { for: "video-file", class: "dropzone" },
    h("strong", {}, "Choose a video"), h("span", {}, " or drop it here"),
    h("span", { class: "hint" }, "MP4, MOV or AVI"), ui.fileName);
  ui.startBtn = h("button", { type: "button", class: "btn btn-primary", disabled: true }, "Upload and analyse");
  ui.stage = h("p", { class: "stage", "aria-live": "polite" });
  ui.progress = h("progress", { max: 1, value: 0, "aria-label": "Progress" });
  ui.progressText = h("span", { class: "bar-value" });
  ui.progressBox = h("div", { class: "progress-box", hidden: true },
    ui.stage, h("div", { class: "bar-row" }, ui.progress, ui.progressText));
  ui.error = h("p", { class: "form-error", role: "alert", hidden: true });

  ui.page = h("div", {},
    pageHeader("Analyse a video", `Subject ${session.consent?.subject_id || "–"}`),
    h("p", { class: "lead" },
      "The video is processed on this computer only. "
      + (keeps
        ? "Storage of the raw video was consented to, so it is kept with the session."
        : "It is deleted as soon as the analysis is finished; only the suggested events are kept.")),
    h("section", { class: "panel" }, ui.input, ui.drop,
      h("div", { class: "actions" }, ui.startBtn), ui.progressBox, ui.error));
  return ui;
}
