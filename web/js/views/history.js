// View: History of saved sessions per subject (confirmed events only).

import { api } from "../api.js";
import { lineChart, stackedBars } from "../charts.js";
import { bpm, duration, emptyState, errorPanel, fmtDate, fmtShortDate, h, pageHeader } from "../dom.js";

function subjectIdOf(s) {
  return typeof s === "string" ? s : (s && (s.subject_id || s.id)) || "";
}

export async function render(root, ctx, params) {
  root.append(pageHeader("History", "Trends of confirmed events across saved sessions."));

  let subjects;
  try {
    subjects = (await api.subjects()).map(subjectIdOf).filter(Boolean);
  } catch (err) {
    root.append(errorPanel(err, "Could not load subjects"));
    return;
  }
  if (!root.isConnected) return;
  if (!subjects.length) {
    root.append(emptyState("No saved sessions yet", "Saved sessions appear here after you review and save them.",
      "#/consent", "Start a session"));
    return;
  }

  const chosen = params[0] && subjects.includes(params[0]) ? params[0] : subjects[0];
  const select = h("select", { id: "subject-select" },
    subjects.map((s) => h("option", { value: s, selected: s === chosen }, s)));
  select.addEventListener("change", () => ctx.navigate(`#/history/${encodeURIComponent(select.value)}`));
  const body = h("div", { "aria-live": "polite" }, h("p", { class: "muted" }, "Loading…"));

  root.append(
    h("section", { class: "panel" },
      h("div", { class: "filters" }, h("label", { for: "subject-select" }, "Subject"), select)),
    body);

  let sessions;
  let trends;
  try {
    [sessions, trends] = await Promise.all([api.subjectSessions(chosen), api.trends(chosen)]);
  } catch (err) {
    body.replaceChildren(errorPanel(err, "Could not load this subject's sessions"));
    return;
  }
  if (!root.isConnected) return;
  body.replaceChildren(...renderSubject(ctx, chosen, sessions || [], trends || []));
}

function renderSubject(ctx, subjectId, sessions, trends) {
  const labels = ctx.config?.event_labels || {};
  const rows = [...trends].sort((a, b) => (a.started_at || 0) - (b.started_at || 0));
  const categories = rows.map((r) => fmtShortDate(r.started_at));
  const kinds = Object.keys(labels).filter((k) => rows.some((r) => Number(r[k]) > 0));

  const out = [];
  const bars = stackedBars({
    categories,
    series: kinds.map((k) => ({ label: labels[k] || k, values: rows.map((r) => Number(r[k]) || 0) })),
    title: `Confirmed events per session for subject ${subjectId}`,
  });
  out.push(h("section", { class: "panel" },
    h("h2", {}, "Confirmed events per session"),
    bars ? h("div", { class: "chart-box" }, bars.chart, bars.legend)
      : h("p", { class: "muted" }, "No confirmed events in the saved sessions.")));

  const hrPoints = rows.map((r, i) => [i, r.mean_heart_rate]).filter((p) => Number(p[1]) > 0);
  const hr = lineChart({
    points: hrPoints, showDots: true, xFormat: (i) => categories[Math.round(i)] || "",
    title: `Mean heart rate per session for subject ${subjectId}`,
  });
  out.push(h("section", { class: "panel" },
    h("h2", {}, "Mean heart rate per session"),
    hr ? h("div", { class: "chart-box" }, hr) : h("p", { class: "muted" }, "Not enough reliable heart-rate data yet.")));

  const sorted = [...sessions].sort((a, b) => (b.started_at || 0) - (a.started_at || 0));
  out.push(h("section", { class: "panel" },
    h("h2", {}, "Sessions"),
    h("div", { class: "table-wrap" },
      h("table", {},
        h("thead", {}, h("tr", {}, ["Date", "Type", "Duration", "Confirmed events", "Mean heart rate", ""]
          .map((c) => h("th", { scope: "col" }, c)))),
        h("tbody", {}, sorted.map((s) => h("tr", {},
          h("td", {}, fmtDate(s.started_at)),
          h("td", {}, s.mode === "video" ? "Video" : "Live"),
          h("td", {}, duration(s.duration_s)),
          h("td", { class: "num" }, String(s.confirmed_events ?? 0)),
          h("td", {}, bpm(s.mean_heart_rate)),
          h("td", {}, h("a", { href: `#/review/stored/${encodeURIComponent(s.session_id)}` }, "Open")))))))));
  return out;
}
