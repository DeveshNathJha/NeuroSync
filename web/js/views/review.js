// View: Review a session. Each suggested event is confirmed or rejected by the professional;
// only confirmed events reach the notes, history and exports.

import { api, download, exportPath, getActiveSession, setActiveSession } from "../api.js";
import { lineChart } from "../charts.js";
import {
  bpm, countOf, duration, emptyState, errorPanel, errorText, fmtDate, h, mmss, notify, pageHeader, pct,
  span, withBusy,
} from "../dom.js";

const STATUS_LABEL = { pending: "Pending", confirmed: "Confirmed", rejected: "Rejected" };
const MODE_LABEL = { llm: "Local LLM", template: "Template" };

export async function render(root, ctx, params) {
  const stored = params[0] === "stored";
  const id = stored ? params[1] : (params[0] || getActiveSession()?.id);
  if (!id) {
    root.append(pageHeader("Review"),
      emptyState("Nothing to review", "Run a live session or analyse a video first, or open a saved session from History.",
        "#/history", "Open history"));
    return;
  }

  let session;
  try {
    session = stored ? await api.stored(id) : await api.session(id);
  } catch (err) {
    root.append(pageHeader("Review"), errorPanel(err, "Could not open this session"));
    return;
  }
  if (!root.isConnected) return;

  const running = session.state === "running" || (session.started_at && !session.ended_at && session.mode === "live");
  const readOnly = stored || running;
  const view = createReview(ctx, session, { id, stored, readOnly });
  root.append(view.page);
  if (running && !stored) {
    view.page.prepend(h("div", { class: "panel panel-warn", role: "status" },
      h("p", {}, "This session is still recording. Stop it before reviewing. "),
      h("a", { href: `#/live/${encodeURIComponent(id)}` }, "Back to the live session")));
  }
}

function createReview(ctx, session, { id, stored, readOnly }) {
  const labels = ctx.config?.event_labels || {};
  const events = Array.isArray(session.events) ? session.events : [];
  const byId = new Map(events.map((e) => [e.id, e]));
  const filter = { kind: "all", status: "all" };

  const el = {
    summary: h("dl", { class: "summary" }),
    chart: h("div", { class: "chart-box" }),
    tbody: h("tbody", {}),
    filterKind: h("select", { id: "filter-kind" }),
    filterStatus: h("select", { id: "filter-status" },
      ["all", "pending", "confirmed", "rejected"].map((v) => h("option", { value: v }, v === "all" ? "All" : STATUS_LABEL[v]))),
  };

  const kinds = [...new Set(events.map((e) => e.kind))];
  el.filterKind.append(h("option", { value: "all" }, "All event types"),
    ...kinds.map((k) => h("option", { value: k }, labels[k] || k)));
  el.filterKind.addEventListener("change", () => { filter.kind = el.filterKind.value; renderTable(); });
  el.filterStatus.addEventListener("change", () => { filter.status = el.filterStatus.value; renderTable(); });

  // -------------------------------------------------------------- summary + chart
  function counts() {
    const c = { pending: 0, confirmed: 0, rejected: 0 };
    for (const e of events) c[e.status] = (c[e.status] || 0) + 1;
    return c;
  }

  function renderSummary() {
    const c = counts();
    const sm = session.summary || {};
    const items = [
      ["Subject", session.consent?.subject_id || sm.subject_id || "–"],
      ["Started", fmtDate(session.started_at)],
      ["Duration", duration(sm.duration_s ?? session.elapsed_s)],
      ["Type", session.mode === "video" ? "Recorded video" : "Live session"],
      ["Suggested", String(events.length)],
      ["Confirmed", String(c.confirmed)],
      ["Rejected", String(c.rejected)],
      ["Pending", String(c.pending)],
      ["Mean heart rate", bpm(sm.mean_heart_rate)],
      ["Resting baseline", bpm(session.baseline_hr ?? sm.baseline_heart_rate)],
    ];
    el.summary.replaceChildren(...items.flatMap(([k, v]) => [h("div", { class: "sum-item" }, h("dt", {}, k), h("dd", {}, v))]));
  }

  function renderChart() {
    const points = (session.heart_rate || []).filter((p) => Array.isArray(p) && Number(p[1]) > 0).map((p) => [p[0], p[1]]);
    const spans = events.filter((e) => e.status !== "rejected")
      .map((e) => ({ start: e.start, end: e.end, status: e.status, label: e.label || labels[e.kind] || e.kind }));
    const chart = lineChart({
      points, spans, yUnit: "", baseline: Number(session.baseline_hr ?? session.summary?.baseline_heart_rate),
      title: "Heart rate during the session; shaded areas are suggested (light) and confirmed (dark) events",
    });
    el.chart.replaceChildren(chart || h("p", { class: "muted" }, "No reliable heart-rate readings in this session."));
  }

  // -------------------------------------------------------------- table
  function visibleEvents() {
    return events.filter((e) => (filter.kind === "all" || e.kind === filter.kind)
      && (filter.status === "all" || e.status === filter.status));
  }

  function linkedText(ev) {
    const linked = (ev.linked || []).map((lid) => byId.get(lid)).filter(Boolean);
    if (!linked.length) return "–";
    return linked.map((o) => `${o.label || labels[o.kind] || o.kind} (${mmss(o.start)})`).join(", ");
  }

  function makeRow(ev) {
    const label = ev.label || labels[ev.kind] || ev.kind;
    const when = ev.span || span(ev.start, ev.end);
    const row = h("tr", { tabindex: 0, dataset: { id: ev.id }, "aria-label": `${label} at ${when}, ${STATUS_LABEL[ev.status] || ev.status}` },
      h("td", { class: "nowrap" }, when),
      h("td", {}, label),
      h("td", { class: "num" }, pct(ev.confidence)),
      h("td", {}, ev.source || "–"),
      h("td", { class: "linked" }, linkedText(ev)),
      h("td", {}, h("span", { class: `pill pill-${ev.status}` }, STATUS_LABEL[ev.status] || ev.status)));

    if (readOnly) {
      row.append(h("td", {}, ev.note || ""));
      return row;
    }
    const note = h("input", {
      type: "text", class: "note", value: ev.note || "", maxlength: 500, "aria-label": `Note for ${label} at ${when}`,
      placeholder: "Add a note",
    });
    note.addEventListener("blur", () => saveNote(ev, note));
    note.addEventListener("keydown", (e) => {
      if (e.key === "Enter") note.blur();
    });
    const btn = (text, status, cls) => h("button", {
      type: "button", class: `btn btn-small ${cls}`, "aria-pressed": String(ev.status === status),
      onclick: () => setStatus(ev, status),
    }, text);
    row.append(
      h("td", { class: "row-actions" },
        btn("Confirm", "confirmed", "btn-ok"),
        btn("Reject", "rejected", "btn-danger"),
        btn("Reset", "pending", "")),
      h("td", {}, note));
    return row;
  }

  function renderTable() {
    const rows = visibleEvents().map(makeRow);
    el.tbody.replaceChildren(...(rows.length ? rows
      : [h("tr", {}, h("td", { colspan: readOnly ? 7 : 8, class: "muted" }, events.length ? "No events match the filter." : "No events were suggested in this session."))]));
  }

  function refreshRow(ev) {
    const old = el.tbody.querySelector(`tr[data-id="${CSS.escape(ev.id)}"]`);
    if (!old) return;
    const hadFocus = old === document.activeElement;
    const fresh = makeRow(ev);
    old.replaceWith(fresh);
    if (hadFocus) fresh.focus();
  }

  function afterChange() {
    ctx.setDirty(true);
    renderSummary();
    renderChart();
  }

  async function setStatus(ev, status) {
    if (ev.status === status) return;
    try {
      await api.patchEvent(id, ev.id, { status, note: ev.note || "" });
      ev.status = status;
      refreshRow(ev);
      afterChange();
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function saveNote(ev, input) {
    const value = input.value.trim();
    if (value === (ev.note || "")) return;
    try {
      await api.patchEvent(id, ev.id, { status: ev.status, note: value });
      ev.note = value;
      ctx.setDirty(true);
    } catch (err) {
      notify(errorText(err), "error");
      input.value = ev.note || "";
    }
  }

  async function bulk(status) {
    const ids = events.filter((e) => e.status === "pending").map((e) => e.id);
    if (!ids.length) {
      notify("There are no pending events.", "info");
      return;
    }
    try {
      await api.bulk(id, { status, event_ids: ids });
      for (const e of events) if (ids.includes(e.id)) e.status = status;
      renderTable();
      afterChange();
      notify(`${ids.length} event${ids.length === 1 ? "" : "s"} ${status}.`, "success");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  // keyboard: c = confirm, r = reject, u = reset, arrows move between rows
  el.tbody.addEventListener("keydown", (e) => {
    const row = e.target.closest("tr[data-id]");
    if (!row || e.target !== row) return;
    const ev = byId.get(row.dataset.id);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = e.key === "ArrowDown" ? row.nextElementSibling : row.previousElementSibling;
      if (next) next.focus();
      return;
    }
    if (readOnly || !ev || e.ctrlKey || e.metaKey || e.altKey) return;
    const key = e.key.toLowerCase();
    if (key === "c") setStatus(ev, "confirmed");
    else if (key === "r") setStatus(ev, "rejected");
    else if (key === "u") setStatus(ev, "pending");
  });

  // -------------------------------------------------------------- notes, exports, save
  const audience = h("select", { id: "audience" },
    h("option", { value: "professional" }, "Professional"),
    h("option", { value: "family" }, "Family (plain language)"));
  const notesOut = h("div", { class: "notes-out", "aria-live": "polite" });

  const notesBtn = h("button", { type: "button", class: "btn btn-primary" }, "Generate notes");
  notesBtn.addEventListener("click", () => withBusy(notesBtn, "Generating…", async () => {
    try {
      const res = await api.notes(id, audience.value);
      const removed = countOf(res.guard_removed);
      notesOut.replaceChildren(
        h("div", { class: "notes-meta" },
          h("span", { class: "badge" }, MODE_LABEL[res.mode] || res.mode || "notes"),
          h("span", { class: "hint" }, removed
            ? `${removed} interpretive statement${removed === 1 ? " was" : "s were"} removed by the language guard.`
            : "No statements needed to be removed.")),
        h("pre", { class: "notes-text" }, res.text || ""));
    } catch (err) {
      notify(errorText(err), "error");
    }
  }));

  const dl = (fmt, text, fallback) => {
    const b = h("button", { type: "button", class: "btn" }, text);
    b.addEventListener("click", () => withBusy(b, "Preparing…", async () => {
      try {
        await download(exportPath(id, fmt, { stored, audience: fmt === "pdf" ? audience.value : undefined }), fallback);
      } catch (err) {
        notify(errorText(err), "error");
      }
    }));
    return b;
  };

  const saveBtn = h("button", { type: "button", class: "btn btn-primary" }, "Save session (encrypted)");
  saveBtn.addEventListener("click", () => withBusy(saveBtn, "Saving…", async () => {
    try {
      const res = await api.save(id);
      ctx.setDirty(false);
      notify(`Session saved and encrypted${res && res.path ? ` (${res.path})` : ""}.`, "success");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }));

  const discardBtn = h("button", { type: "button", class: "btn btn-danger" }, "Discard without saving");
  discardBtn.addEventListener("click", () => {
    if (!window.confirm("Discard this session? Its suggested events and your review will be lost.")) return;
    withBusy(discardBtn, "Discarding…", async () => {
      try {
        await api.discard(id);
        if (getActiveSession()?.id === id) setActiveSession(null);
        ctx.setDirty(false);
        notify("Session discarded.", "success");
        ctx.refreshStatus?.();
        ctx.navigate("#/consent");
      } catch (err) {
        notify(errorText(err), "error");
      }
    });
  });

  // -------------------------------------------------------------- layout
  const headCells = ["Time", "Event", "Confidence", "Source", "Happened with", "Status"]
    .concat(readOnly ? ["Note"] : ["Review", "Note"]);
  const table = h("div", { class: "table-wrap" },
    h("table", { class: "events" },
      h("caption", { class: "visually-hidden" }, "Suggested events"),
      h("thead", {}, h("tr", {}, headCells.map((c) => h("th", { scope: "col" }, c)))),
      el.tbody));

  const page = h("div", { class: "review" },
    pageHeader(stored ? "Saved session (read-only)" : "Review", `Session ${session.id || id}`),
    h("section", { class: "panel" }, el.summary),
    h("section", { class: "panel" }, h("h2", {}, "Heart rate and events"), el.chart),
    h("section", { class: "panel" },
      h("h2", {}, "Suggested events"),
      readOnly ? null : h("p", { class: "hint" },
        "Every event is a suggestion. Confirm what you observed, reject the rest. Keyboard: focus a row, then C = confirm, R = reject, U = reset, ↑/↓ to move."),
      h("div", { class: "filters" },
        h("label", { for: "filter-kind" }, "Type"), el.filterKind,
        h("label", { for: "filter-status" }, "Status"), el.filterStatus,
        readOnly ? null : h("div", { class: "toolbar-actions" },
          h("button", { type: "button", class: "btn", onclick: () => bulk("confirmed") }, "Confirm all pending"),
          h("button", { type: "button", class: "btn", onclick: () => bulk("rejected") }, "Reject all pending"))),
      table),
    h("section", { class: "panel" },
      h("h2", {}, "Observation notes & exports"),
      h("p", { class: "hint" }, "Notes and exports contain confirmed events only."),
      h("div", { class: "filters" }, h("label", { for: "audience" }, "Audience"), audience,
        stored ? null : notesBtn),
      stored ? null : notesOut,
      h("div", { class: "actions" },
        dl("pdf", "Download PDF", `neurosync-${id}.pdf`),
        dl("csv", "Download CSV", `neurosync-${id}.csv`),
        dl("fhir", "Download FHIR JSON", `neurosync-${id}.fhir.json`))),
    readOnly ? null : h("section", { class: "panel" },
      h("h2", {}, "Session"),
      h("p", { class: "hint" }, "Saving stores the session and your review encrypted on this computer."),
      h("div", { class: "actions" }, saveBtn, discardBtn)));

  renderSummary();
  renderChart();
  renderTable();
  return { page };
}
