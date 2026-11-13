// View: Data & privacy: where data lives, erasure, export, retention, audit log.

import { api, download, subjectExportPath } from "../api.js";
import { duration, errorPanel, errorText, fmtDate, h, notify, pageHeader, withBusy } from "../dom.js";

function subjectIdOf(s) {
  return typeof s === "string" ? s : (s && (s.subject_id || s.id)) || "";
}

function codeRow(label, value) {
  return h("div", { class: "sum-item" }, h("dt", {}, label), h("dd", {}, h("code", {}, value || "–")));
}

export async function render(root, ctx) {
  root.append(pageHeader("Data & privacy", "Everything is stored on this computer, encrypted."));

  const infoBox = h("section", { class: "panel" }, h("h2", {}, "Where your data is"), h("p", { class: "muted" }, "Loading…"));
  const subjectsBox = h("section", { class: "panel" }, h("h2", {}, "Subjects"), h("p", { class: "muted" }, "Loading…"));
  const retentionBox = buildRetention(ctx, () => reloadSubjects());
  const auditBox = h("section", { class: "panel" }, h("h2", {}, "Audit log"), h("p", { class: "muted" }, "Loading…"));
  root.append(infoBox, subjectsBox, retentionBox, auditBox);

  async function reloadSubjects() {
    try {
      const subjects = (await api.subjects()).map(subjectIdOf).filter(Boolean);
      if (!root.isConnected) return;
      subjectsBox.replaceChildren(...buildSubjects(subjects, reloadAll));
    } catch (err) {
      subjectsBox.replaceChildren(h("h2", {}, "Subjects"), errorPanel(err, "Could not load subjects"));
    }
  }

  async function reloadAudit() {
    try {
      const [entries, verify] = await Promise.all([api.audit(200), api.auditVerify()]);
      if (!root.isConnected) return;
      auditBox.replaceChildren(...buildAudit(entries || [], verify));
    } catch (err) {
      auditBox.replaceChildren(h("h2", {}, "Audit log"), errorPanel(err, "Could not load the audit log"));
    }
  }

  async function reloadAll() {
    await Promise.all([reloadSubjects(), reloadAudit()]);
  }

  try {
    const info = await api.dataInfo();
    if (!root.isConnected) return;
    infoBox.replaceChildren(
      h("h2", {}, "Where your data is"),
      h("p", {}, "Sessions are encrypted with a key that is created on this computer and kept outside the "
        + "application folder. Anyone with access to this computer account can open the app, so keep the account protected."),
      h("dl", { class: "summary" },
        codeRow("Data folder", info.data_dir),
        codeRow("Encryption key", info.key_path),
        codeRow("Sessions", info.sessions_dir),
        codeRow("Audit log", info.audit_path)));
  } catch (err) {
    infoBox.replaceChildren(h("h2", {}, "Where your data is"), errorPanel(err, "Could not load data locations"));
  }
  await reloadAll();
}

function buildSubjects(subjects, reloadAll) {
  if (!subjects.length) return [h("h2", {}, "Subjects"), h("p", { class: "muted" }, "No saved sessions.")];

  const select = h("select", { id: "data-subject" }, subjects.map((s) => h("option", { value: s }, s)));
  const sessionsBox = h("div", { "aria-live": "polite" });
  const confirmInput = h("input", { id: "erase-confirm", autocomplete: "off", "aria-describedby": "erase-hint" });
  const eraseBtn = h("button", { type: "button", class: "btn btn-danger", disabled: true }, "Erase all data of this subject");
  const exportBtn = h("button", { type: "button", class: "btn" }, "Export subject data (JSON)");

  const syncErase = () => { eraseBtn.disabled = confirmInput.value.trim() !== select.value; };
  confirmInput.addEventListener("input", syncErase);

  async function loadSessions() {
    sessionsBox.replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try {
      const sessions = await api.subjectSessions(select.value);
      sessionsBox.replaceChildren(sessionsTable(sessions || [], async (sid, btn) => {
        if (!window.confirm("Delete this saved session permanently?")) return;
        await withBusy(btn, "Deleting…", async () => {
          try {
            await api.deleteStored(sid);
            notify("Session deleted.", "success");
            await reloadAll();
          } catch (err) {
            notify(errorText(err), "error");
          }
        });
      }));
    } catch (err) {
      sessionsBox.replaceChildren(errorPanel(err, "Could not load sessions"));
    }
  }

  select.addEventListener("change", () => {
    confirmInput.value = "";
    syncErase();
    loadSessions();
  });

  exportBtn.addEventListener("click", () => withBusy(exportBtn, "Exporting…", async () => {
    try {
      await download(subjectExportPath(select.value), `neurosync-subject-${select.value}.json`);
    } catch (err) {
      notify(errorText(err), "error");
    }
  }));

  eraseBtn.addEventListener("click", () => {
    const subject = select.value;
    if (confirmInput.value.trim() !== subject) return;
    if (!window.confirm(`Erase every saved session of subject ${subject}? This cannot be undone.`)) return;
    withBusy(eraseBtn, "Erasing…", async () => {
      try {
        const res = await api.deleteSubject(subject);
        const n = res && (res.deleted ?? res.count ?? res.sessions_deleted);
        notify(`All data of subject ${subject} was erased${Number.isFinite(n) ? ` (${n} sessions)` : ""}.`, "success");
        await reloadAll();
      } catch (err) {
        notify(errorText(err), "error");
      }
    });
  });

  loadSessions();
  return [
    h("h2", {}, "Subjects"),
    h("div", { class: "filters" }, h("label", { for: "data-subject" }, "Subject"), select, exportBtn),
    sessionsBox,
    h("div", { class: "danger-zone" },
      h("h3", {}, "Erase a subject (right to erasure)"),
      h("label", { for: "erase-confirm" }, "Type the subject id to confirm"),
      confirmInput,
      h("p", { class: "hint", id: "erase-hint" }, "The audit log keeps only the fact that an erasure happened."),
      eraseBtn),
  ];
}

function sessionsTable(sessions, onDelete) {
  if (!sessions.length) return h("p", { class: "muted" }, "No saved sessions for this subject.");
  const sorted = [...sessions].sort((a, b) => (b.started_at || 0) - (a.started_at || 0));
  return h("div", { class: "table-wrap" },
    h("table", {},
      h("thead", {}, h("tr", {}, ["Date", "Duration", "Confirmed events", ""].map((c) => h("th", { scope: "col" }, c)))),
      h("tbody", {}, sorted.map((s) => {
        const del = h("button", { type: "button", class: "btn btn-small btn-danger" }, "Delete");
        del.addEventListener("click", () => onDelete(s.session_id, del));
        return h("tr", {},
          h("td", {}, fmtDate(s.started_at)),
          h("td", {}, duration(s.duration_s)),
          h("td", { class: "num" }, String(s.confirmed_events ?? 0)),
          h("td", { class: "row-actions" },
            h("a", { class: "btn btn-small", href: `#/review/stored/${encodeURIComponent(s.session_id)}` }, "Open"), del));
      }))));
}

function buildRetention(ctx, onDone) {
  const days = ctx.config?.retention_days ?? 365;
  const btn = h("button", { type: "button", class: "btn btn-danger" }, `Delete sessions older than ${days} days`);
  btn.addEventListener("click", () => {
    if (!window.confirm(`Permanently delete all saved sessions older than ${days} days?`)) return;
    withBusy(btn, "Deleting…", async () => {
      try {
        const res = await api.purge();
        const n = typeof res === "number" ? res : res && (res.deleted ?? res.purged ?? res.count);
        notify(Number.isFinite(n) ? `${n} old session${n === 1 ? "" : "s"} deleted.` : "Retention purge finished.", "success");
        await onDone();
      } catch (err) {
        notify(errorText(err), "error");
      }
    });
  });
  return h("section", { class: "panel" },
    h("h2", {}, "Retention"),
    h("p", {}, `Sessions are kept for ${days} days unless you delete them earlier.`),
    btn);
}

function auditTime(entry) {
  const raw = entry.time || entry.timestamp || entry.ts;
  if (!raw) return "–";
  const d = typeof raw === "number" ? new Date(raw * 1000) : new Date(raw);
  return Number.isNaN(d.getTime()) ? String(raw) : d.toLocaleString();
}

function buildAudit(entries, verify) {
  const intact = verify && verify.intact;
  const badge = h("span", { class: `badge ${intact ? "badge-ok" : "badge-bad"}`, role: "status" },
    intact ? "Integrity check passed" : "Integrity check failed: the log was modified");
  const rows = entries.map((e) => h("tr", {},
    h("td", { class: "nowrap" }, auditTime(e)),
    h("td", {}, e.action || "–"),
    h("td", {}, e.actor || "–"),
    h("td", {}, e.subject_id || "–"),
    h("td", {}, e.session_id || "–"),
    h("td", {}, e.details || "")));
  return [
    h("h2", {}, "Audit log ", badge),
    h("p", { class: "hint" }, "Each entry is chained to the previous one with a SHA-256 hash, so changes are detectable. "
      + "Only ids and actions are logged, never notes or video."),
    rows.length
      ? h("div", { class: "table-wrap" },
        h("table", {},
          h("thead", {}, h("tr", {}, ["Time", "Action", "By", "Subject", "Session", "Details"].map((c) => h("th", { scope: "col" }, c)))),
          h("tbody", {}, rows)))
      : h("p", { class: "muted" }, "The audit log is empty."),
  ];
}
